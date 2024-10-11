import os
from ifcopenshell.api import run
import ifcopenshell.api
import ifcopenshell.api.geometry
import ifcopenshell
import ifcopenshell.api.geometry.assign_representation
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import numpy as np
from shapely.geometry import Polygon

from . import global_variables as gvars
from .elements import *


class IFCModelHandler:
    def __init__(self):
        self.model = None
        self.body = None
        self.storey = None
        self.library_filename = os.path.join(gvars.root_folder, "resources", "object_library.ifc")
        self.library_model = None
        self.type_names_to_ifc_object_types = {}
        self.object_type_wc = None
        self.object_type_sink = None
        self.object_type_shower = None
        self.object_type_bath = None
        self.object_type_bed_single = None
        self.object_type_bed_double = None
        self.object_type_outlet = None



    def create_project(self):
        self.model = ifcopenshell.file()
        project = run("root.create_entity", self.model, ifc_class="IfcProject", name="My Project")
        run("unit.assign_unit", self.model)
        context = run("context.add_context", self.model, context_type="Model")
        self.body = run("context.add_context", self.model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context)
        site = run("root.create_entity", self.model, ifc_class="IfcSite", name="My Site")
        building = run("root.create_entity", self.model, ifc_class="IfcBuilding", name="My Building")
        self.storey = run("root.create_entity", self.model, ifc_class="IfcBuildingStorey", name="FloorPlan")
        self.storey.Elevation = 0.0
        run("geometry.edit_object_placement", self.model, product=self.storey)
        run("aggregate.assign_object", self.model, relating_object=project, products=[site])
        run("aggregate.assign_object", self.model, relating_object=site, products=[building])
        run("aggregate.assign_object", self.model, relating_object=building, products=[self.storey])


    def convert_to_ifc_units(self, value):
        if isinstance(value, (int, float)):
            return value * gvars.scale_2d_to_ifc
        elif isinstance(value, (list, tuple)):
            return [self.convert_to_ifc_units(v) for v in value]
        else:
            return value
        

    def create_ifc_walls_from_polygons(self, walls_list):

        default_wall_style = self.create_color_style("Default Wall Style", 0.9, 0.9, 0.7)
        ifc_walls = []

        for wall in walls_list:
            ifc_walls.append(self.create_wall(wall, gvars.default_wall_height, f"wall_{wall.id}", style=default_wall_style))

        run("spatial.assign_container", self.model, relating_structure=self.storey, products=ifc_walls)


    def create_ifc_spaces_from_enclosed_areas(self, rooms:list[Room]):

        space_styles = []
        for room_cat in RoomCategory:
            space_style = self.create_color_style(f"{room_cat.name} Space Style", room_cat.color[0],  room_cat.color[1],  room_cat.color[2], transparency=0.5)
            space_styles.append(space_style)


        ifc_space_count = 0

        for room in rooms:
            if len(room.polygon.exterior.coords) < 3:
                continue

            style = space_styles[room.category.id]
            self.create_space(room.id, room, gvars.default_space_height, room.name, style=style)
            ifc_space_count += 1



    def create_ifc_zones_for_housing_types(self, housings:list[Housing]):
        zone_count = 0
        for housing in housings:
            area = housing.area * gvars.scale_2d_to_ifc ** 2
            ifc_zone = self.model.create_entity(
                "IfcZone",
                **{
                    "GlobalId": ifcopenshell.guid.new(),
                    "OwnerHistory": ifcopenshell.api.run("owner.create_owner_history", self.model),
                    "Name": f"Logement {housing.id} ({housing.type})",
                    "Description": f"Area: {str(round(area, 2))} m²",
                }
            )

            run("group.assign_group", self.model, products=[room.ifc_element for room in housing.rooms], group=ifc_zone)
            zone_count += 1


    def create_wall(self, wall, height, name="default_wall", style=None):

        ifc_wall = run("root.create_entity", self.model, ifc_class="IfcWall", predefined_type="STANDARD")
        ifc_wall.Name = name
        run("geometry.edit_object_placement", self.model, product=ifc_wall)

        corners = self.convert_to_ifc_units(wall.polygon.exterior.coords[:-1])
        representation = self.assign_extrusion_representation(ifc_wall, corners, height, style=style)

        if style:
            ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=representation, styles=[style])
        wall.ifc_element = ifc_wall

        return ifc_wall


    def assign_extrusion_representation(self, ifc_element, corners, height, elevation=0, style=None):
        
        if corners[0] != corners[-1]:
            corners.append(corners[0])

        corners_as_floats = [(float(round(x, 3)), -float(round(y, 3))) for x, y in corners]
        base = run("profile.add_arbitrary_profile", self.model, profile=corners_as_floats) # Fonction modifiée dans librairie IfcOpenShell

        if height < 0:
            height = height * -1
            direction = self.model.createIfcDirection((0., 0., -1.))
        else:
            direction = self.model.createIfcDirection((0., 0., 1.))

        axis_placement = None

        if elevation:
            direction_x = self.model.createIfcDirection((1., 0., 0.))
            placement_point = self.model.createIfcCartesianPoint((0.0, 0.0, float(elevation)))
            axis_placement = self.model.createIfcAxis2Placement3D(placement_point, direction, direction_x)
            # extrusion = self.model.createIfcExtrudedAreaSolid(SweptArea=base, ExtrudedDirection=direction, Depth=height, Position=axis_placement)

        extrusion = self.model.createIfcExtrudedAreaSolid(SweptArea=base, ExtrudedDirection=direction, Depth=height, Position=axis_placement)
        representation = self.model.createIfcShapeRepresentation(ContextOfItems=self.body, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[extrusion])
        run("geometry.assign_representation", self.model, product=ifc_element, representation=representation)
        return representation


    def create_color_style(self, name, red, green, blue, transparency=0.0):
        style = ifcopenshell.api.run("style.add_style", self.model, name=name)
        ifcopenshell.api.run("style.add_surface_style", self.model, style=style, ifc_class="IfcSurfaceStyleShading", attributes={
                    "SurfaceColour": { "Name": None, "Red": red, "Green": green, "Blue": blue },
                    "Transparency": transparency,
                })
        return style


    def create_space(self, space_id, room, height, name, style=None):

        # polygon_coords = convert_to_ifc_units(list(room.polygon.exterior.coords))
        ifc_space = run("root.create_entity", self.model, ifc_class="IfcSpace", predefined_type="INTERNAL")
        ifc_space.Name = name
        ifc_space.ObjectType =  name
        ifc_space.CompositionType = "ELEMENT"
        ifc_space.LongName = str(space_id)
        area = room.polygon.area * gvars.scale_2d_to_ifc ** 2
        # area = Polygon(polygon_coords).area
        ifc_space.Description = f"Area: {str(round(area, 2))} m²"

        run("geometry.edit_object_placement", self.model, product=ifc_space)
        run("aggregate.assign_object", self.model, products=[ifc_space], relating_object=self.storey)

        corners = self.convert_to_ifc_units(list(room.polygon.exterior.coords))
        representation = self.assign_extrusion_representation(ifc_space, corners, height, style=style)

        if style:
            ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=representation, styles=[style])

        room.ifc_element = ifc_space


    def create_opening(self, door, height, sill_height, name, ifc_class, ifc_type, style=None):
        ifc_door = run("root.create_entity", self.model, ifc_class=ifc_class, predefined_type=ifc_type)
        ifc_door.Name = name
        run("geometry.edit_object_placement", self.model, product=ifc_door)

        corners = self.convert_to_ifc_units(door.get_corners())
        representation = self.assign_extrusion_representation(ifc_door, corners, height, elevation=sill_height)

        if style:
            ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=representation, styles=[style])

        door.ifc_element = ifc_door
        return ifc_door


    def create_ifc_openings_from_polygons(self, openings_list:list[Opening]):
        default_door_style = self.create_color_style("Default Door Style", 0.9, 0.5, 0.2)
        default_window_style = self.create_color_style("Default Window Style", 0.6, 0.8, 1.0, transparency=0.7)
        ifc_openings = []
        door_count = 0
        window_count = 0

        for opening in openings_list:
            if opening.classname == "window":
                style = default_window_style
                height = gvars.default_window_height
                sill_height = gvars.default_window_sill_height
                ifc_class = "IfcWindow"
                ifc_type = "WINDOW"
                window_count += 1 
            else:
                style = default_door_style
                height = gvars.default_door_height
                sill_height = 0.0
                ifc_class = "IfcDoor"
                ifc_type = "DOOR"
                door_count += 1

            ifc_openings.append(self.create_opening(opening, height, sill_height, f"opening_{opening.id}", ifc_class, ifc_type, style=style))
            corresponding_wall = opening.corresponding_wall if opening.corresponding_wall.is_subwall == False else opening.corresponding_wall.parent_wall
            self.add_opening_to_wall(corresponding_wall, opening, height, sill_height)

        run("spatial.assign_container", self.model, relating_structure=self.storey, products=ifc_openings)


    def add_opening_to_wall(self, wall, opening:Polygon, height, sill_height):
        ifc_opening = run("root.create_entity", self.model, ifc_class="IfcOpeningElement", name=f"opening_{opening.id}")
        corners = self.convert_to_ifc_units(opening.get_corners(thickness=wall.thickness + 10))
        self.assign_extrusion_representation(ifc_opening, corners, height, elevation=sill_height)
        run("void.add_opening", self.model, opening=ifc_opening, element=wall.ifc_element)
        ifcopenshell.api.run("void.add_filling", self.model, opening=ifc_opening, element=opening.ifc_element)
        ifc_opening.ObjectType = "Opening"
        run("geometry.edit_object_placement", self.model, product=ifc_opening)


    def create_electrical_devices(self, elem_list:list[Outlet]):
        
        default_electrical_obj_style = self.create_color_style("Default Electrical Object Style", 1.0, 0.6, 0.6)
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["outlet-simple"].RepresentationMaps[0].MappedRepresentation, styles=[default_electrical_obj_style])
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["outlet-rj45"].RepresentationMaps[0].MappedRepresentation, styles=[default_electrical_obj_style])

        elec_devices_count = 0
        for elem in elem_list:
            ifc_elem = self.create_generic_object(elem, f"outlet_{elem.id}", style=default_electrical_obj_style)
            self.replace_generic_object_with_specific_type(elem, ifc_elem, self.type_names_to_ifc_object_types[elem.ifc_type_name], elevation=gvars.default_outlet_height/1000)
            elec_devices_count += 1


    def create_ifc_objects(self, obj_list:list[Object]):

        default_sanitary_obj_style = self.create_color_style("Default Sanitary Object Style", 0.3, 0.6, 1.0)
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["wc"].RepresentationMaps[0].MappedRepresentation, styles=[default_sanitary_obj_style])
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["sink"].RepresentationMaps[0].MappedRepresentation, styles=[default_sanitary_obj_style])
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["shower"].RepresentationMaps[0].MappedRepresentation, styles=[default_sanitary_obj_style])
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["bathtub"].RepresentationMaps[0].MappedRepresentation, styles=[default_sanitary_obj_style])

        default_furniture_obj_style = self.create_color_style("Default Furniture Object Style", 0.3, 1.0, 0.6)
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["bed-single"].RepresentationMaps[0].MappedRepresentation, styles=[default_furniture_obj_style])
        ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=self.type_names_to_ifc_object_types["bed-double"].RepresentationMaps[0].MappedRepresentation, styles=[default_furniture_obj_style])

        obj_count = 0
        for obj in obj_list:
            obj_ifc = self.create_generic_object(obj, f"{obj.classname}_{obj.id}", style=None)
            self.replace_generic_object_with_specific_type(obj, obj_ifc, self.type_names_to_ifc_object_types[obj.ifc_type_name])
            obj_count += 1


    def replace_generic_object_with_specific_type(self, obj, obj_ifc, specific_obj_type, style=None, elevation=0.0):
        run("type.assign_type", self.model, related_objects=[obj_ifc], relating_type=specific_obj_type)
        origin_point = self.convert_to_ifc_units(obj.origin_point)
        location_matrix = np.eye(4)
        angle_deg = round(obj.angle * -1 * 180/np.pi)
        location_matrix = ifcopenshell.util.placement.rotation(angle_deg, "Z") @ location_matrix
        location_matrix[:,3][0:3] = (origin_point[0], -origin_point[1], elevation)
        run("geometry.edit_object_placement", self.model, product=obj_ifc, matrix=location_matrix)


    def create_generic_object(self, generic_obj, name="default_generic_obj", style=None):

        ifc_obj = run("root.create_entity", self.model, ifc_class=generic_obj.ifc_class, predefined_type=generic_obj.ifc_predefined_type)
        ifc_obj.Name = name
        if generic_obj.contained_in_room and generic_obj.contained_in_room.ifc_element:
            run("spatial.assign_container", self.model, relating_structure=generic_obj.contained_in_room.ifc_element, products=[ifc_obj])
        else:
            run("spatial.assign_container", self.model, relating_structure=self.storey, products=[ifc_obj])

        generic_obj.ifc_element = ifc_obj

        return ifc_obj


    def create_slab(self, polygon, thickness, name, style=None):

        ifc_slab = run("root.create_entity", self.model, ifc_class="IfcSlab")
        ifc_slab.Name = name
        run("spatial.assign_container", self.model, relating_structure=self.storey, products=[ifc_slab])
        run("geometry.edit_object_placement", self.model, product=ifc_slab)
        ifc_slab.PredefinedType = "FLOOR"
        polygon_coords = self.convert_to_ifc_units(list(polygon.exterior.coords))
        representation = self.assign_extrusion_representation(ifc_slab, polygon_coords, -thickness)

        if style:
            ifcopenshell.api.run("style.assign_representation_styles", self.model, shape_representation=representation, styles=[style])


    def save_ifc(self, filename=f"{gvars.root_folder}/output/pred_model.ifc"):
        self.model.write(filename)


    def get_library_object_type(self, name):
        for obj_type in self.library_model.by_type("IfcTypeObject"):
            if name.lower() == obj_type.Name.lower():
                return obj_type
            

    def load_library_file(self):
        try:
            self.library_model = ifcopenshell.open(self.library_filename)
        except:
            self.library_model = ifcopenshell.open(os.path.basename(self.library_filename))

        ifc_type_names = [
            "wc", "sink", "shower", "bathtub", "bed-single", "bed-double", "outlet-simple", "outlet-rj45"
        ]

        for ifc_type_name in ifc_type_names:
            source_objtype = self.get_library_object_type(ifc_type_name)
            self.type_names_to_ifc_object_types[ifc_type_name] = self.model.add(source_objtype)
