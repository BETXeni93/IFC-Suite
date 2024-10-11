from __future__ import annotations

from enum import Enum
import os
import numpy as np
from shapely import MultiLineString
from shapely.geometry import Polygon, LineString, Point, MultiPoint
from shapely.affinity import translate
import cv2

from . import global_variables as gvars


class ElementsManager:

    def __init__(self):
        self.nodes: list[Node] = []
        self.node_id_counter = 0
        self.wall_id_counter = 0
        self.room_id_counter = 0
        self.opening_id_counter = 0
        self.object_id_counter = 0
        self.outlet_id_counter = 0
        self.housing_id_counter = 0
    

class Node:

    def __init__(self, manager:ElementsManager, position, connections=None):   # connections = [(wall, index (0 if start 1 if end)), ...]

        self.node_id = manager.node_id_counter
        self.position: tuple[int, int] = position
        self.connections: list[Wall, float] = connections if connections else []
        self.previously_visited_nodes_for_enclosed_area_detection = []
        manager.nodes.append(self)
        manager.node_id_counter += 1

    def remove(self, manager:ElementsManager):
        for connection in self.connections:
            wall = connection[0]
            wall.connected_nodes[connection[1]] = None
        manager.nodes.remove(self)

class Wall:

    def __init__(self, manager:ElementsManager, polygon:Polygon, line:tuple[2], thickness, wall_id=None):
        if wall_id is not None:
            self.id = wall_id
        else:
            self.id = manager.wall_id_counter
        self.line:tuple[2] = line
        self.line_with_offsets:tuple[2] = None
        self.thickness = thickness
        self.polygon = polygon
        self.ifc_element = None
        self.connected_nodes:list[Node, float] = [] # (connected_node, dist_from_start)
        # self.connected_nodes: list[Node, Node] = [None, None] # ([connected_node_to_start_point], [connected_node_to_end_point])
        self.extension:list[Wall, Wall] = [None, None] # Extensions start/end, created when joining a wall that was already joined with other wall
        self.subwalls: list[Wall] = []
        self.is_subwall: bool = False
        self.parent_wall = None
        self.openings: list[Opening] = []
        manager.wall_id_counter = max(manager.wall_id_counter + 1, self.id + 1)
        self.manager = manager

        # if line is same points, raise error
        if line[0] == line[1]:
            raise ValueError("Wall line cannot have same points")


    def get_corners(self):
        return list(self.polygon.exterior.coords[:-1])


    def create_subwall(self, polygon, line:tuple[2], thickness):
        subwall = Wall(self.manager, polygon, line, thickness, wall_id=None)
        subwall.is_subwall = True

        if self.is_subwall:
            subwall.parent_wall = self.parent_wall
            if self in self.parent_wall.subwalls:
                self.parent_wall.subwalls.remove(self)
        else:
            subwall.parent_wall = self

        subwall.parent_wall.subwalls.append(subwall)
        return subwall
    

    def is_wall_start_connected(self):
        if self.connected_nodes:
            node, distance = self.connected_nodes[0]
            if distance < 1:
                return True
        return False
    
    def is_wall_end_connected(self):
        if self.connected_nodes:
            node, distance = self.connected_nodes[-1]
            if distance > self.get_length() - 1:
                return True
        return False


    def connect_to_node(self, node:Node, distance_from_start):
        self.connected_nodes.append([node, distance_from_start])
        node.connections.append([self, distance_from_start])
        self.connected_nodes = sorted(self.connected_nodes, key=lambda x: x[1])

    def connect_to_node_old(self, node:Node, point_index):
        self.connected_nodes[point_index] = node
        node.connections.append([self, point_index])

    def get_next_node(self, node:Node):
        for i, (node_i, dist_from_start) in enumerate(self.connected_nodes):
            if node == node_i:
                if i < len(self.connected_nodes) - 1:
                    return self.connected_nodes[i + 1][0]
        return None
    
    def get_previous_node(self, node:Node):
        for i, (node_i, dist_from_start) in enumerate(self.connected_nodes):
            if node == node_i:
                if i > 0:
                    return self.connected_nodes[i - 1][0]
        return None

        
    def get_length(self):
        p1, p2 = self.line
        return np.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
    

    def get_angle(self, direction_insenstive=False, to_degrees=False):
        p1, p2 = self.line
        angle = np.arctan2(p2[1] - p1[1], p2[0] - p1[0])
        if direction_insenstive:
            angle = angle % np.pi

        if to_degrees:
            return angle * 180 / np.pi
        else:
            return angle
        

class RoomCategory(Enum): # (id, code, name, color)     
    UNDEFINED = (0, "indefini", "Indéfini", (0.5, 0.5, 0.5))
    SHAFT = (1, "gt", "GT", (0.8, 0.2, 1.0))
    EXTERIOR = (2, "exterieur", "Extérieur", (0.5, 0.8, 0.8))
    ACCESS = (3, "circulation", "Circulation", (0.2, 0.3, 0.2))
    HALLWAY = (4, "couloir", "Couloir", (0.2, 0.8, 1.0))
    STAIRS = (5, "escalier", "Escalier", (0.2, 0.3, 0.2))
    ELEVATOR = (6, "ascenseur", "Ascenseur", (0.2, 0.3, 0.2))
    STORAGE = (7, "rangement", "Rangement", (0.2, 0.8, 1.0))
    LAUNDRY = (8, "buanderie", "Buanderie", (0.2, 0.8, 1.0))
    WC = (9, "wc", "WC", (0.5, 1.0, 0.5))
    BATHROOM = (10, "sdb", "SDB", (0.5, 1.0, 0.5))
    KITCHEN = (11, "cuisine", "Cuisine", (1.0, 0.5, 0.5))
    LIVINGROOM = (12, "sejour", "Séjour", (1.0, 0.5, 0.5))
    BEDROOM = (13, "chambre", "Chambre", (0.5, 0.5, 1.0))
    # Tri de la moins prioritaire à la plus prioritaire (ex, si on trouve une étiquette Couloir et une étiquette Séjour, on prendra la Séjour)

    @property
    def id(self):
        return self.value[0]
    
    @property
    def code(self):
        return self.value[1]

    @property
    def name(self):
        return self.value[2]
    
    @property
    def color(self):
        return self.value[3]
    
    def find_by_code(code):
        for category in RoomCategory:
            if category.code == code:
                return category
        return RoomCategory.UNDEFINED
    

class Room:

    def __init__(self, manager:ElementsManager, polygon, room_id=None, name = "default_room", category = RoomCategory.UNDEFINED):
        if room_id is not None:
            self.id = room_id
        else:
            self.id = manager.room_id_counter

        self.polygon:Polygon = polygon
        self.ifc_element = None
        self.name = name
        self.surrounding_nodes: list[Node] = []
        self.surrounding_walls: list[Wall] = []
        self.is_adjusted = False
        self.contains_objects: list[Object] = []
        self.category:RoomCategory = category
        self.doors: list[Opening] = []
        self.windows: list[Opening] = []
        self.linearization = [] # [side0 [Object0, (start,end)], [Object1, (start,end)], ...], ...]        
        self.connected_rooms: list[Room] = []
        self.part_of_housing = None
        self.roomsides: list[RoomSide] = []
        manager.room_id_counter = max(manager.room_id_counter + 1, self.id + 1)    

    def get_corners(self):
        return list(self.polygon.exterior.coords[:-1])

    def coords_to_string(self):
        return str(list((round(coord[0]), round(coord[1])) for coord in self.polygon.exterior.coords))
    

    def set_category(self):

        room_cointains_sink = False

        if self.polygon.area < gvars.max_gt_area and not self.contains_objects:
            self.category = RoomCategory.SHAFT
        
        if self.category == RoomCategory.UNDEFINED:
            for obj in self.contains_objects:
                if obj.classname == "bed":
                    self.category = RoomCategory.BEDROOM
                    break
                elif obj.classname in ["wc", "shower", "bath"]:
                    self.category = RoomCategory.BATHROOM
                    break
                elif obj.classname == "sink":
                    room_cointains_sink = True

            if self.category == RoomCategory.UNDEFINED:  
                if room_cointains_sink:
                    self.category = RoomCategory.LIVINGROOM
                else:
                    self.category = RoomCategory.UNDEFINED
        
        self.name = self.category.name


    def set_category_from_cls_id(self, cls_id):

        if cls_id == 1:
            self.category = RoomCategory.LIVINGROOM
        elif cls_id == 2:
            self.category = RoomCategory.LIVINGROOM
        elif cls_id == 3:
            self.category = RoomCategory.KITCHEN
        elif cls_id == 4:
            self.category = RoomCategory.BEDROOM
        elif cls_id == 5:
            self.category = RoomCategory.BATHROOM
        elif cls_id == 6:
            self.category = RoomCategory.WC
        elif cls_id == 7:
            self.category = RoomCategory.HALLWAY
        elif cls_id == 8:
            self.category = RoomCategory.STORAGE
        elif cls_id == 9:
            self.category = RoomCategory.EXTERIOR
        elif cls_id == 10:
            self.category = RoomCategory.ACCESS
        elif cls_id == 11:
            self.category = RoomCategory.ELEVATOR
        elif cls_id == 12:
            self.category = RoomCategory.STAIRS
        elif cls_id == 13:
            self.category = RoomCategory.SHAFT
        else:
            self.category = RoomCategory.UNDEFINED

        self.name = self.category.name


    def get_intserection_with_room_side(self, roomside, obj, polygon:Polygon, img=None):
        if polygon.intersects(roomside.linestring):
            intersection_line = polygon.intersection(roomside.linestring)
            if intersection_line.geom_type == 'LineString':
                intersection_line = [intersection_line.coords[0], intersection_line.coords[1]]
                color = gvars.colors[obj.id % len(gvars.colors)]
                if img is not None:
                    cv2.line(img, (round(intersection_line[0][0]), round(intersection_line[0][1])), (round(intersection_line[1][0]), round(intersection_line[1][1])), color, 2)
                angle_intersection = np.degrees(np.arctan2(intersection_line[1][1] - intersection_line[0][1], intersection_line[1][0] - intersection_line[0][0]))
                if abs(angle_intersection - roomside.angle_deg) > 90:
                    intersection_line = intersection_line[::-1] # Points clockwise
                return intersection_line
        return None


    def linearize(self, img, print_details=False) :
    
        room_coords = list(self.polygon.exterior.coords)
        for i in range(len(room_coords) - 1):
            p1 = room_coords[i]
            p2 = room_coords[(i + 1) % len(room_coords)]
            roomside = RoomSide(self, i, (p1, p2))
            self.roomsides.append(roomside)

            for obj in self.contains_objects:
                buffered_polygon = obj.polygon.buffer(0.07 / gvars.scale_2d_to_ifc)
                intersection_line = self.get_intserection_with_room_side(roomside, obj, buffered_polygon, img)
                if intersection_line:
                    roomside.add_element(obj, intersection_line)

            for window in self.windows:
                window_polygon = window.get_polygon(thickness=window.corresponding_wall.thickness + (0.2/gvars.scale_2d_to_ifc))
                intersection_line = self.get_intserection_with_room_side(roomside, window, window_polygon, img)
                if intersection_line:
                    roomside.add_element(window, intersection_line)
            
            for door in self.doors:
                door_polygon = door.get_polygon(thickness=door.corresponding_wall.thickness + (0.2/gvars.scale_2d_to_ifc))
                intersection_line = self.get_intserection_with_room_side(roomside, door, door_polygon, img)
                if intersection_line:
                    roomside.add_element(door, intersection_line)


    def get_longest_roomsides(self, number):
        return sorted(self.roomsides, key=lambda x: x.length, reverse=True)[:number]


    
class RoomSide:

    def __init__(self, room, index, line:tuple[2]):
        self.room = room
        self.index = index
        self.line = ((round(line[0][0]), round(line[0][1])), (round(line[1][0]), round(line[1][1])))
        self.contained_elements: list[tuple[2]] = [] # [(element, position on side), ...]
        self.linestring = LineString(line)
        self.length = round(self.linestring.length)
        self.angle_deg = np.degrees(np.arctan2(line[1][1] - line[0][1], line[1][0] - line[0][0]))
        

    def add_element(self, element, position_line:tuple[2]):
            
            position_start_end_on_side = None

            if isinstance(element, Object) or isinstance(element, Opening):
                position_start_end_on_side = (self.get_position_on_side(position_line[0]), self.get_position_on_side(position_line[1]))
            elif isinstance(element, Outlet):
                pos_start = max(0, self.get_position_on_side(position_line) - 5)
                pos_end = min(self.get_position_on_side(position_line) + 5, self.length)
                position_start_end_on_side = (pos_start, pos_end)

            if position_start_end_on_side:
                self.contained_elements.append((element, position_start_end_on_side))


    def get_position_on_side(self, point:tuple[2]):
        return self.linestring.project(Point(point))
    

    def get_coordinates_from_position(self, position):
        if position > self.length or position < 0:
            return None
        else:
            return self.linestring.interpolate(position).coords[0]
        
    
    def is_position_valid(self, position):
        if position < 0 or position > self.length:
            return False
        for elem in self.contained_elements:
            if elem[1][0] <= position <= elem[1][1]:
                return False
        return True


class Opening:

    def __init__(self, manager:ElementsManager, center_point, corresponding_wall:Wall, length, opening_id=None, classname="door", score=0.0):
        if opening_id is not None:
            self.id = opening_id
        else:
            self.id = manager.opening_id_counter
        self.center_point = center_point
        self.corresponding_wall: Wall = corresponding_wall
        corresponding_wall.openings.append(self)     
        self.length = length
        self.ifc_element = None
        manager.opening_id_counter = max(manager.opening_id_counter + 1, self.id + 1)
        self.polygon:Polygon = self.get_polygon()
        self.classname = classname
        self.connects_rooms: list[Room, Room] = [None, None]
        self.score = score


    def find_adjacent_rooms(self, rooms_list: list[Room]):

        ortho_dist = self.corresponding_wall.thickness / 2 + (0.3 / gvars.scale_2d_to_ifc)
        ortho_angle = (self.corresponding_wall.get_angle(direction_insenstive=True, to_degrees=False) + np.pi/2) % np.pi
        p1 = (self.center_point[0] + ortho_dist * np.cos(ortho_angle), self.center_point[1] + ortho_dist * np.sin(ortho_angle))
        p2 = (self.center_point[0] - ortho_dist * np.cos(ortho_angle), self.center_point[1] - ortho_dist * np.sin(ortho_angle))

        room1, room2 = None, None
        for room in rooms_list:
            if room.polygon.contains(Point(p1)):
                room1 = room
            elif room.polygon.contains(Point(p2)):
                room2 = room

        self.connects_rooms[0] = room1
        self.connects_rooms[1] = room2

        if self.classname == "door":
            if room1 is not None and self not in room1.doors:
                room1.doors.append(self)
            if room2 is not None and self not in room2.doors:
                room2.doors.append(self)
        elif self.classname == "window":
            if room1 is not None and self not in room1.windows:
                room1.windows.append(self)
            if room2 is not None and self not in room2.windows:
                room2.windows.append(self)

        if room1 is not None and room2 is not None:
            if room2 not in room1.connected_rooms:
                room1.connected_rooms.append(room2)
            if room1 not in room2.connected_rooms:
                room2.connected_rooms.append(room1)

        return self.connects_rooms[0], self.connects_rooms[1]
    

    def get_polygon(self, thickness=None):
        if thickness is None:
            thickness = gvars.default_opening_thickness/(gvars.scale_2d_to_ifc*1000)
        wall_angle = self.corresponding_wall.get_angle()
        half_length = (self.length / 2) - 1
        p1 = (self.center_point[0] + half_length * np.cos(wall_angle), self.center_point[1] + half_length * np.sin(wall_angle))
        p2 = (self.center_point[0] - half_length * np.cos(wall_angle), self.center_point[1] - half_length * np.sin(wall_angle))
        
        half_thickness = thickness / 2 # (self.corresponding_wall.thickness / 2) + 1
        p1g = (p1[0] - half_thickness * np.sin(wall_angle), p1[1] + half_thickness * np.cos(wall_angle))
        p1d = (p1[0] + half_thickness * np.sin(wall_angle), p1[1] - half_thickness * np.cos(wall_angle))
        p2d = (p2[0] + half_thickness * np.sin(wall_angle), p2[1] - half_thickness * np.cos(wall_angle))
        p2g = (p2[0] - half_thickness * np.sin(wall_angle), p2[1] + half_thickness * np.cos(wall_angle))

        return Polygon([p1g, p1d, p2d, p2g])
    

    def get_corners(self, thickness=None):
        return list(self.get_polygon(thickness).exterior.coords[:-1])
        
class ObjectSideAgainstWall(Enum):
    LONG = 0
    SHORT = 1
    ANY = 2
    NONE = 3

class Object:

    def __init__(self, manager:ElementsManager, classname, shapely_polygon:Polygon, obj_id=None, score=0.0):

        if obj_id is not None:
            self.id = obj_id
        else:
            self.id = manager.object_id_counter
        self.classname = classname
        self.typename = "undefined"
        self.ifc_class = "IfcBuildingElementProxy"
        self.ifc_predefined_type = "NOTDEFINED"
        self.ifc_type_name = "undefined"
        self.shortest_edge_length = gvars.shortest_edge_length_default
        self.shortest_long_edge_length = None
        self.side_against_wall = ObjectSideAgainstWall.ANY
        self.polygon = shapely_polygon
        self.ifc_element = None
        self.origin_point = self.get_center_point()
        self.angle = 0
        self.depth = 0
        self.width = 0
        self.contained_in_room:Room = None
        self.score = score
        manager.object_id_counter = max(manager.object_id_counter + 1, self.id + 1)


        if classname in ["bed", "furniture"]:
            self.ifc_class = "IfcFurnishingElement"
            if classname == "bed":
                self.ifc_predefined_type = "BED"
                self.ifc_type_name = "bed-double"
                self.ifc_obj_width = 1.60 / gvars.scale_2d_to_ifc # 0.90 single bed
                self.ifc_obj_depth = 2.00 / gvars.scale_2d_to_ifc # 1.90 single bed
                self.shortest_edge_length = gvars.shortest_edge_length_bed
                self.shortest_long_edge_length = gvars.shortest_long_edge_length_bed
                self.side_against_wall = ObjectSideAgainstWall.SHORT


        elif classname in ["sink", "wc", "shower", "bath"]:
            self.ifc_class = "IfcSanitaryTerminal"
            if classname == "sink":
                self.ifc_predefined_type = "SINK"
                self.ifc_type_name = "sink"
                self.ifc_obj_width = 0.60 / gvars.scale_2d_to_ifc
                self.ifc_obj_depth = 0.45 / gvars.scale_2d_to_ifc
                self.shortest_edge_length = gvars.shortest_edge_length_sink
                self.side_against_wall = ObjectSideAgainstWall.ANY
            elif classname == "wc":
                self.ifc_predefined_type = "TOILETPAN"
                self.ifc_type_name = "wc"
                self.ifc_obj_width = 0.37 / gvars.scale_2d_to_ifc
                self.ifc_obj_depth = 0.54 / gvars.scale_2d_to_ifc
                self.shortest_edge_length = gvars.shortest_edge_length_wc
                self.side_against_wall = ObjectSideAgainstWall.SHORT
            elif classname == "shower":
                self.ifc_predefined_type = "SHOWER"
                self.ifc_type_name = "shower"
                self.ifc_obj_width = 0.90 / gvars.scale_2d_to_ifc
                self.ifc_obj_depth = 0.90 / gvars.scale_2d_to_ifc
                self.shortest_edge_length = gvars.shortest_edge_length_shower
                self.side_against_wall = ObjectSideAgainstWall.ANY
            elif classname == "bath":
                self.ifc_predefined_type = "BATH"
                self.ifc_type_name = "bathtub"
                self.ifc_obj_width = 1.70 / gvars.scale_2d_to_ifc
                self.ifc_obj_depth = 0.70 / gvars.scale_2d_to_ifc
                self.shortest_edge_length = gvars.shortest_edge_length_bath
                self.side_against_wall = ObjectSideAgainstWall.LONG


    def get_center_point(self):
        return self.polygon.centroid.coords[0]
    

    def get_corners(self):
        return list(self.polygon.exterior.coords[:-1])
    

    def get_relative_corners(self):
        origin = self.origin_point
        corners = list(self.polygon.exterior.coords[:-1])
        return [(corner[0] - origin[0], corner[1] - origin[1]) for corner in corners]
    

    def set_room_container(self, rooms_list: list[Room]):
        for room in rooms_list:
            if room.polygon.contains(Point(self.get_center_point())):
                self.contained_in_room = room
                room.contains_objects.append(self)
                break


    def set_origin_point_and_angle(self, img, walls_list, walls_tree):

        sides_to_check = []
        set_next_to_wall = False
        attenant_wall = None
        center_point = self.get_center_point()
        coords = list(self.polygon.exterior.coords)
        sides = [LineString([coords[i], coords[i+1]]).length for i in range(4)]       
        max_side_idx = sides.index(max(sides))
        min_side_idx = sides.index(min(sides))
        if min_side_idx == max_side_idx: # cas où le polygone est carré
            max_side_idx = (max_side_idx + 1) % 4
        if self.side_against_wall in [ObjectSideAgainstWall.SHORT, ObjectSideAgainstWall.ANY]: # ortho_to_longer_side:
            main_side = LineString([coords[max_side_idx], coords[(max_side_idx + 1) % 4]])
            sides_to_check.append(main_side)
            self.depth = sides[max_side_idx]
            self.width = sides[min_side_idx]
        if self.side_against_wall in [ObjectSideAgainstWall.LONG, ObjectSideAgainstWall.ANY]:
            main_side = LineString([coords[min_side_idx], coords[(min_side_idx + 1) % 4]])
            sides_to_check.append(main_side)
            self.depth = sides[min_side_idx]
            self.width = sides[max_side_idx]

        if self.classname == "bed":
            if self.width < 1.2 / gvars.scale_2d_to_ifc:
                self.typename = "single"
                self.ifc_type_name = "bed-single"
                self.ifc_obj_width = 0.90 / gvars.scale_2d_to_ifc
                self.ifc_obj_depth = 1.90 / gvars.scale_2d_to_ifc
            else:
                self.typename = "double"

        xd = (main_side.coords[1][0] - main_side.coords[0][0]) / 2
        yd = (main_side.coords[1][1] - main_side.coords[0][1]) / 2
        angle = np.arctan2(yd, xd)
        self.angle = angle
        def_origin_point = Point(center_point[0] + xd, center_point[1] + yd)                 
        origin_point = def_origin_point # Point(center_point)

        intersections = []

        for main_side in sides_to_check:

            length = (main_side.length/2) + 0.5/gvars.scale_2d_to_ifc
                
            dx, dy = main_side.coords[1][0] - main_side.coords[0][0], main_side.coords[1][1] - main_side.coords[0][1]
            angle = np.arctan2(dy, dx)
            dx = np.cos(angle) * length
            dy = np.sin(angle) * length
            p1 = Point(center_point[0] - dx, center_point[1] - dy)
            p2 = Point(center_point[0] + dx, center_point[1] + dy)
            extension_line = LineString([p1, p2])
            cv2.line(img, (int(p1.x), int(p1.y)), (int(p2.x), int(p2.y)), (0, 128, 0), 1)

            if self.contained_in_room is not None:

                intersections_found_with_surronding_walls = False

                if not intersections_found_with_surronding_walls:
                    room_linearring = self.contained_in_room.polygon.exterior
                    room_lines = MultiLineString([LineString([room_linearring.coords[i], room_linearring.coords[i+1]]) for i in range(len(room_linearring.coords) - 1)])
                    for room_line in room_lines.geoms:
                        intersection = room_line.intersection(extension_line)
                        if not intersection.is_empty:
                            if isinstance(intersection, Point):
                                intersections.append((intersection, room_line))
                            elif isinstance(intersection, MultiPoint):
                                for point in intersection.geoms:
                                    intersections.append((point, room_line))


            else:
                interecting_indices = walls_tree.query(self.polygon.buffer(1/gvars.scale_2d_to_ifc))
                for idx in interecting_indices:
                    wall = walls_list[idx]
                    wall_extorior_line1 = LineString([wall.polygon.exterior.coords[0], wall.polygon.exterior.coords[1]])
                    wall_extorior_line2 = LineString([wall.polygon.exterior.coords[2], wall.polygon.exterior.coords[3]])
                    wall_exterior_lines = MultiLineString([wall_extorior_line1, wall_extorior_line2])
                    intersection = wall_exterior_lines.intersection(extension_line) # wall.polygon.exterior.intersection(extension_line)
                    if not intersection.is_empty:
                        if isinstance(intersection, Point):
                            intersections.append((intersection, wall))
                        elif isinstance(intersection, MultiPoint):
                            for point in intersection.geoms:
                                intersections.append((point, wall))


        room_line_angle = None
        max_dist = 0
        if intersections:
            max_dist = 100000
            for inter_point, wall in intersections:
                dist = Point(center_point).distance(inter_point)
                if dist < max_dist:
                    set_next_to_wall = True
                    max_dist = dist
                    origin_point = inter_point
                    if isinstance(wall, Wall):
                        attenant_wall:Wall = wall
                    elif isinstance(wall, LineString):
                        room_line_angle = np.arctan2(wall.coords[1][1] - wall.coords[0][1], wall.coords[1][0] - wall.coords[0][0])

        self.origin_point = origin_point.coords[0]


        # Calculer l'angle orienté par rapport à l'axe vertical orienté vers le bas (0, -1), sens horaire

        # dx, dy = self.origin_point[0] - center_point[0], self.origin_point[1] - center_point[1]
        dx, dy = center_point[0] - self.origin_point[0], center_point[1] - self.origin_point[1]
        angle_obj = np.arctan2(dy, dx)

        attenant_wall_angle = None
        if attenant_wall is not None:
            attenant_wall_angle = attenant_wall.get_angle()
        elif room_line_angle is not None:
            attenant_wall_angle = room_line_angle

        if attenant_wall_angle is not None:
            angle_to_wall1 = attenant_wall_angle - np.pi/2 if attenant_wall_angle > 0 else attenant_wall_angle + np.pi/2
            if angle_to_wall1 > 0 :# np.pi/4:
                angle_to_wall2 =  angle_to_wall1 - np.pi
            else:
                angle_to_wall2 = angle_to_wall1 + np.pi
            if abs(((angle_obj - angle_to_wall1) + np.pi) % (2*np.pi) - np.pi) < abs(((angle_obj - angle_to_wall2) + np.pi) % (2*np.pi) - np.pi):
                angle = angle_to_wall1
            else:
                angle = angle_to_wall2
        else:
            angle = angle_obj

        angle_to_vertical = angle - np.pi/2
        self.angle = angle_to_vertical

        if max_dist != 0:
            delta_x = -dx*(max_dist - main_side.length/2)/max_dist
            delta_y = -dy*(max_dist - main_side.length/2)/max_dist
            self.polygon = translate(self.polygon, xoff=delta_x, yoff=delta_y)

        return extension_line, origin_point, set_next_to_wall
    

class Outlet:

    symbol_path = os.path.join(gvars.root_folder, 'assets\\prise.png')
    symbol_origin_point = (-6, 32)
    ifc_type_name = "outlet-simple"
    ifc_class = "IfcOutlet"
    ifc_predefined_type = "POWEROUTLET"

    def __init__(self, manager:ElementsManager, x, y, angle, room:Room, roomside:RoomSide, obj_id=None):

        if obj_id is not None:
            self.id = obj_id
        else:
            self.id = manager.outlet_id_counter

        self.x = round(x)
        self.y = round(y)
        self.origin_point = (self.x, self.y)
        self.angle = angle # angle en rad orienté par rapport à l'axe vertical orienté vers le bas (0, -1)
        self.ifc_element = None
        self.contained_in_room = room
        roomside.add_element(self, [x,y])
        self.symbol_lateral_offset = 0 # en pixels
        manager.outlet_id_counter = max(manager.outlet_id_counter + 1, self.id + 1)

class RJ45(Outlet):

    symbol_path = os.path.join(gvars.root_folder, 'assets\\prise_rj45.png')
    symbol_origin_point = (-10, 32)
    ifc_type_name = "outlet-rj45"
    ifc_predefined_type = "DATAOUTLET"

    def __init__(self, manager:ElementsManager, x, y, angle, room: Room, roomside: RoomSide, obj_id=None):
        super().__init__(manager, x, y, angle, room, roomside, obj_id)


class Housing:

    def __init__(self, manager:ElementsManager, id=None):
        self.rooms: list[Room] = []
        self.type = "undefined"
        self.area = 0

        if id is not None:
            self.id = id
        else:
            self.id = manager.housing_id_counter
        manager.housing_id_counter = max(manager.housing_id_counter + 1, self.id + 1)


    def add_room(self, room: Room):
        self.rooms.append(room)
        room.part_of_housing = self
        self.type = self.process_housing_type()
        self.area = self.process_area()


    def process_housing_type(self):
        room_categories = [room.category for room in self.rooms]
        number_of_bedrooms = room_categories.count(RoomCategory.BEDROOM)
        type = "T" + str(number_of_bedrooms + 1)
        return type


    def process_area(self):
        area = sum([room.polygon.area for room in self.rooms])
        return area
