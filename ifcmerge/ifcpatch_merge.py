import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit as unit
import logger


class Merger:
    def __init__(self,
                 logger, 
                 file, 
                 source, 
                 merge_sites=True, 
                 merge_buildings=True, 
                 lvls_mgmt=0, 
                 remove_empty_containers=True
                 ):

        self.logger = logger
        self.file = file
        self.source = source
        self.merge_sites = merge_sites
        self.merge_buildings = merge_buildings
        self.lvls_mgmt = lvls_mgmt
        self.remove_empty_containers = remove_empty_containers
        self.dict_original_prj_units = None
        self.dict_merged_prj_units = None


    def merge(self):

        self.logger.printlog("  Patch start")
        self.existing_contexts = self.file.by_type("IfcGeometricRepresentationContext")
        original_agreggates = self.file.by_type('IfcRelAggregates')
        original_project = self.file.by_type("IfcProject")[0]

        original_sites = self.file.by_type("IfcSite")
        if original_sites:
            original_site = original_sites[0]
        else:
            self.logger.printlog("  No site in original model")
            self.merge_sites = False
            self.merge_buildings = False

        original_buildings = self.file.by_type("IfcBuilding")
        if original_buildings:
            original_building = self.file.by_type("IfcBuilding")[0]
        else:
            self.logger.printlog("  No building in original model")
            self.merge_buildings = False

        original_storeys = self.file.by_type("IfcBuildingStorey")


        # A FAIRE : CONVERTIR LES PROPERTIES + TOUS LES AREA ET VOLUME
        self.dict_original_prj_units = self.get_prj_units_dict(self.file)
        self.dict_merged_prj_units = self.get_prj_units_dict(self.source)
        self.convert_units_if_needed()

        self.added_contexts = set()

        merged_project = self.file.add(self.source.by_type("IfcProject")[0])
        
        self.logger.printlog("  Transfering all representation contexts")
        self.logger.printlog("  ...")
        for element in self.source.by_type("IfcGeometricRepresentationContext"):
            new = self.file.add(element)
            self.added_contexts.add(new)
        self.logger.printlog("  Done")
        self.logger.printlog()

        elements_error_list = []
        self.logger.printlog(f"  Transfering all elements")
        self.logger.printlog("  ...")
        for element in self.source:
            # self.logger.printlog(f"  add elem: {element}")      
            try:
                self.file.add(element)
            except Exception as ex:
                self.logger.printlog(f"  add elem: {element}")
                self.logger.printlog(f"    ERROR: {ex}")
                if not self.manage_transfer_error(element):
                    elements_error_list.append(element)

        if elements_error_list:
            self.logger.printlog()
            self.logger.printlog(f"  PROCESSING ERROR LIST, try to add failed elements again | length={len(elements_error_list)}")
            self.logger.printlog()
            for element in elements_error_list:
                self.logger.printlog(f"    add elem: {element}")
                try:
                    self.file.add(element)
                    self.logger.printlog("      Success")
                except Exception as ex:
                    self.logger.printlog(f"      ERROR: {ex}")

        self.logger.printlog("  Done")
        self.logger.printlog()
        
        merged_sites = []

        if hasattr(merged_project, "IsDecomposedBy") and merged_project.IsDecomposedBy:
            for decomp in merged_project.IsDecomposedBy:
                for rel_obj in decomp.RelatedObjects:
                    if rel_obj.is_a("IfcSite"):
                        merged_sites.append(rel_obj)

        # for site in self.file.by_type("IfcSite"):
        #     if site in original_sites:
        #         continue
        #     if hasattr(site, "Decomposes") and site.Decomposes:
        #         for decomp in site.Decomposes:
        #             if hasattr(decomp,"RelatingObject") and decomp.RelatingObject:
        #                 if site.Decomposes.RelatingObject.is_a("IfcProject"):
        #                     merged_sites.append(site)
        
        self.logger.printlog(merged_sites)

        # merged_sites = self.subtract_lists(self.file.by_type("IfcSite"), original_sites)
        merged_buildings = self.subtract_lists(self.file.by_type("IfcBuilding"), original_buildings)
        merged_storeys = self.subtract_lists(self.file.by_type("IfcBuildingStorey"), original_storeys)

        self.logger.printlog("  Setting IfcRelAggregates")
        self.logger.printlog("  ...")
        for agr in self.file.by_type('IfcRelAggregates'):
            if agr in original_agreggates:   

                # A FAIRE : GERER LES BUILDINGS DANS LES BUILDINGS :
                # https://standards.buildingsmart.org/IFC/RELEASE/IFC2x3/TC1/HTML/ifcproductextension/lexical/ifcspatialstructureelement.htm

                if self.merge_sites:
                    # Rel: Original Site > Merged Buildings
                    if agr.RelatingObject == original_site:
                        for merged_building in merged_buildings:
                            agr.RelatedObjects = agr.RelatedObjects + (merged_building,)
                else:
                    # Rel: Original Project > Merged Site
                    if agr.RelatingObject == original_project:
                         for merged_site in merged_sites:
                            agr.RelatedObjects = agr.RelatedObjects + (merged_site,)

                if self.merge_buildings:
                    # Rel: Orginal Building > Merged Storeys
                    if agr.RelatingObject == original_building:
                        for merged_storey in merged_storeys:
                            agr.RelatedObjects = agr.RelatedObjects + (merged_storey,)

            else:
                
                # Remove Rel: Merged Proj > Merged Site
                if agr.RelatingObject == merged_project:
                    self.file.remove(agr)
                    continue

                if self.merge_sites:
                    # Remove Rel: Merged Site > Merged Building
                    if agr.RelatingObject in merged_sites:
                        self.file.remove(agr)
                        continue

                if self.merge_buildings:
                    # Remove Rel: Merged Building > Merged Storeys
                    if agr.RelatingObject in merged_buildings:
                        self.file.remove(agr)
                        continue

        self.file.remove(merged_project)
        if self.merge_sites:
            for merged_site in merged_sites:
                self.file.remove(merged_site)
        if self.merge_buildings:
            for merged_building in merged_buildings:
                self.file.remove(merged_building)

        self.logger.printlog("  Done")
        self.logger.printlog()


        self.logger.printlog(f"  Merging levels")
        if self.lvls_mgmt == 0:
           self.merge_levels_by_elevation(merged_storeys, original_storeys)
        elif self.lvls_mgmt == 1:
           self.merge_levels_by_name(merged_storeys, original_storeys)

        self.logger.printlog("  Done")
        self.logger.printlog()

        self.logger.printlog("  Reusing existing contexts")
        self.logger.printlog("  ...")
        self.reuse_existing_contexts()
        self.logger.printlog("  Done")
        self.logger.printlog()

        if self.remove_empty_containers:
            self.logger.printlog("  Purging empty containers")
            self.logger.printlog("  ...")
            self.purge_containers()
            self.logger.printlog("  Done")

        return self.file
    
    def merge_levels_by_elevation(self, merged_storeys, original_storeys):
        self.logger.printlog("  By elevation")
        for merged_storey in merged_storeys:
            storey_to_merge_into = None
            if hasattr(merged_storey, "Elevation") and (merged_storey.Elevation is not None):
                merged_global_elevation = 0
                loc_placement = merged_storey.ObjectPlacement
                while(hasattr(loc_placement, "PlacementRelTo") and loc_placement.PlacementRelTo):
                    merged_global_elevation += loc_placement.RelativePlacement.Location.Coordinates[2]
                    loc_placement = loc_placement.PlacementRelTo
                merged_global_elevation += loc_placement.RelativePlacement.Location.Coordinates[2]
                self.logger.printlog(f"    Child level [Name: {merged_storey.Name} | GlobalElevation: {round(merged_global_elevation, 5)}]")

                for original_storey in original_storeys:
                    if hasattr(original_storey, "Elevation") and (original_storey.Elevation is not None):
                        original_global_elevation = 0
                        loc_placement = original_storey.ObjectPlacement
                        while(hasattr(loc_placement, "PlacementRelTo") and loc_placement.PlacementRelTo):
                            original_global_elevation += loc_placement.RelativePlacement.Location.Coordinates[2]
                            loc_placement = loc_placement.PlacementRelTo
                        original_global_elevation += loc_placement.RelativePlacement.Location.Coordinates[2]
                        # self.logger.printlog(f"    Parent level [Name: {original_storey.Name} | GlobalElevation: {round(original_global_elevation, 5)}]")
                        if (abs(original_global_elevation - merged_global_elevation) < 1e-5):
                            storey_to_merge_into = original_storey
                            break
                    # if hasattr(original_storey, "Elevation") and (original_storey.Elevation is not None):
                    #     if (abs(original_storey.Elevation - merged_storey.Elevation) < 1e-5):
                    #         storey_to_merge_into = original_storey
                    #         break

            if storey_to_merge_into:
                self.logger.printlog(f"    -> Corresponding level (same global elevation) was found in parent model: [Name: {storey_to_merge_into.Name} | Elevation: {round(storey_to_merge_into.Elevation, 5)}]")
                self.merge_storeys(merged_storey, storey_to_merge_into)
            # else:
            #     for original_storey in original_storeys:
            #         if hasattr(original_storey, "Elevation") and (original_storey.Elevation is not None):

            #             original_global_elevation = original_storey.Elevation
            #             loc_placement = original_storey.ObjectPlacement
            #             while(hasattr(loc_placement, "PlacementRelTo") and loc_placement.PlacementRelTo):
            #                 original_global_elevation += loc_placement.RelativePlacement.Location.Coordinates[2]
            #                 loc_placement = loc_placement.PlacementRelTo

            #             merged_global_elevation = merged_storey.Elevation
            #             loc_placement = merged_storey.ObjectPlacement
            #             while(hasattr(loc_placement, "PlacementRelTo") and loc_placement.PlacementRelTo):
            #                 merged_global_elevation += loc_placement.RelativePlacement.Location.Coordinates[2]
            #                 loc_placement = loc_placement.PlacementRelTo

            #             if (abs(original_global_elevation - merged_global_elevation) < 1e-5):
            #                 storey_to_merge_into = original_storey
            #                 break
            #     if storey_to_merge_into:
            #         self.logger.printlog(f"    -> Corresponding level (same global elevation) was found in parent model: [Name: {storey_to_merge_into.Name} | Elevation: {round(storey_to_merge_into.Elevation, 5)}]")
            #         self.merge_storeys(merged_storey, storey_to_merge_into)
            #     else:
            #         self.logger.printlog(f"    -> No level with same elevation was found. Child level was copied into parent model")
            else:
                self.logger.printlog(f"    -> No level with same elevation was found. Child level was copied into parent model")

    def merge_levels_by_name(self, merged_storeys, original_storeys):
        self.logger.printlog("  By name")
        for merged_storey in merged_storeys:
            self.logger.printlog(f"    Child level [Name: {merged_storey.Name} | Elevation: {round(merged_storey.Elevation, 5)}]")
            storey_to_merge_into = None
            if hasattr(merged_storey, "Name") and merged_storey.Name:
                for original_storey in original_storeys:
                    if hasattr(original_storey, "Name") and original_storey.Name:
                        if original_storey.Name == merged_storey.Name:
                            storey_to_merge_into = original_storey
                            break

            if storey_to_merge_into:
                self.logger.printlog(f"    -> Corresponding level (same name) was found in parent model: [Name: {storey_to_merge_into.Name} | Elevation: {round(storey_to_merge_into.Elevation, 5)}]")
                self.merge_storeys(merged_storey, storey_to_merge_into)
            else:
                self.logger.printlog(f"    -> No level with same name was found. Child level was copied into parent model")

    

    def convert_units_if_needed(self):
        original_length_unit = self.dict_original_prj_units["LENGTHUNIT"]
        merged_length_unit = self.dict_merged_prj_units["LENGTHUNIT"]
        original_prefix = ""
        if hasattr(original_length_unit,"Prefix"):
            original_prefix = original_length_unit.Prefix if original_length_unit.Prefix else ""
        original_length_unit_name = original_prefix + original_length_unit.Name
        
        merged_prefix = ""
        if hasattr(merged_length_unit,"Prefix"):
            merged_prefix = merged_length_unit.Prefix if merged_length_unit.Prefix else ""
        merged_length_unit_name = merged_prefix + merged_length_unit.Name

        if (original_prefix != merged_prefix) or (original_length_unit.Name != merged_length_unit.Name):
            self.logger.printlog(f"  Converting length units from {merged_length_unit_name} to {original_length_unit_name}")
            self.logger.printlog(f"    Converting length units in attributes ...")
            self.convert_length_units_of_all_elements(self.source, merged_length_unit, original_length_unit)
            self.logger.printlog(f"    Converting length units in properties ...")
            self.convert_length_units_in_properties(self.source, merged_length_unit, original_length_unit)
            self.logger.printlog("  Done")
            self.logger.printlog()
        else:
            self.logger.printlog(f"  No need to convert length units (same units in both models: {merged_length_unit_name})")


    def reuse_existing_contexts(self):
        to_delete = set()
        for added_context in self.added_contexts:
            equivalent_existing_context = self.get_equivalent_existing_context(added_context)
            if equivalent_existing_context:
                for inverse in self.file.get_inverse(added_context):
                    ifcopenshell.util.element.replace_attribute(inverse, added_context, equivalent_existing_context)
                to_delete.add(added_context)

        for added_context in to_delete:
            ifcopenshell.util.element.remove_deep2(self.file, added_context)


    def get_equivalent_existing_context(self, added_context):
        for context in self.existing_contexts:
            if context.is_a() != added_context.is_a():
                continue
            if context.is_a("IfcGeometricRepresentationSubContext"):
                if (
                    context.ContextType == added_context.ContextType
                    and context.ContextIdentifier == added_context.ContextIdentifier
                    and context.TargetView == added_context.TargetView
                ):
                    return context
            elif (
                context.ContextType == added_context.ContextType
                and context.ContextIdentifier == added_context.ContextIdentifier
            ):
                return context
            

    def merge_storeys(self, merged_storey, storey_to_merge_into):

         # Elements référencés par le niveau
        if hasattr(merged_storey, "ContainsElements") and merged_storey.ContainsElements:      
            merged_contained_elements = ()
            for rel_cont in merged_storey.ContainsElements:
                merged_contained_elements += rel_cont.RelatedElements
                self.file.remove(rel_cont)
            if hasattr(storey_to_merge_into, "ContainsElements") and storey_to_merge_into.ContainsElements:  
                original_contained_elements = storey_to_merge_into.ContainsElements[0].RelatedElements
                storey_to_merge_into.ContainsElements[0].RelatedElements = original_contained_elements + merged_contained_elements
            else:
                self.file.create_entity(
                    "IfcRelContainedInSpatialStructure",
                    **{
                        "GlobalId": ifcopenshell.guid.new(),
                        "OwnerHistory": ifcopenshell.api.run("owner.create_owner_history", self.file),
                        "RelatedElements": merged_contained_elements,
                        "RelatingStructure": storey_to_merge_into,
                    },
                )
        # Containers dans niveau (IfcSpaces)
        if hasattr(merged_storey, "IsDecomposedBy") and merged_storey.IsDecomposedBy:      
            merged_decomposed_elements = ()
            for rel_agg in merged_storey.IsDecomposedBy:
                merged_decomposed_elements += rel_agg.RelatedObjects
                self.file.remove(rel_agg)
            if hasattr(storey_to_merge_into, "IsDecomposedBy") and storey_to_merge_into.IsDecomposedBy: 
                original_decomposed_elements = storey_to_merge_into.IsDecomposedBy[0].RelatedObjects
                storey_to_merge_into.IsDecomposedBy[0].RelatedObjects = original_decomposed_elements + merged_decomposed_elements
            else:
                self.file.create_entity(
                    "IfcRelAggregates",
                    **{
                        "GlobalId": ifcopenshell.guid.new(),
                        "OwnerHistory": ifcopenshell.api.run("owner.create_owner_history", self.file),
                        "RelatedObjects": merged_decomposed_elements,
                        "RelatingObject": storey_to_merge_into,
                    },
                )

        # self.replace_local_placements(merged_storey, storey_to_merge_into)
            
        self.file.remove(merged_storey)

    def replace_local_placements(self, merged_storey, storey_to_merge_into):
        # Fonctionne pas avec maquettes ['Vinci Immo - Ile Seguin SL1-A-CDX-ARC #1 2020-04-17 1512.ifc', 'Vinci Immo - Ile Seguin SL1-C-XTU-ARCC #1 2020-04-17 1513.ifc']
        # (pb d'angle de coordinnées?) + certiainement pb de WorldCoordinateSystem
        # Replace LocalPlacement of elements in merged storey placement hierarchy
        # Manage case where the storey to merge into is not at the XY location than the merged storey
        if hasattr(merged_storey.ObjectPlacement, "ReferencedByPlacements") and merged_storey.ObjectPlacement.ReferencedByPlacements:
            original_global_X = 0
            original_global_Y = 0
            loc_placement = storey_to_merge_into.ObjectPlacement
            while(hasattr(loc_placement, "PlacementRelTo") and loc_placement.PlacementRelTo):
                original_global_X += loc_placement.RelativePlacement.Location.Coordinates[0]
                original_global_Y += loc_placement.RelativePlacement.Location.Coordinates[1]
                loc_placement = loc_placement.PlacementRelTo
            original_global_X += loc_placement.RelativePlacement.Location.Coordinates[0]
            original_global_Y += loc_placement.RelativePlacement.Location.Coordinates[1]

            merged_global_X = 0
            merged_global_Y = 0
            loc_placement = merged_storey.ObjectPlacement
            while(hasattr(loc_placement, "PlacementRelTo") and loc_placement.PlacementRelTo):
                merged_global_X += loc_placement.RelativePlacement.Location.Coordinates[0]
                merged_global_Y += loc_placement.RelativePlacement.Location.Coordinates[1]
                loc_placement = loc_placement.PlacementRelTo
            merged_global_X += loc_placement.RelativePlacement.Location.Coordinates[0]
            merged_global_Y += loc_placement.RelativePlacement.Location.Coordinates[1]

            # original_length_unit = self.dict_original_prj_units["LENGTHUNIT"]
            # merged_length_unit = self.dict_merged_prj_units["LENGTHUNIT"]
            # merged_global_X = unit.convert_unit(merged_global_X, merged_length_unit, original_length_unit)
            # merged_global_Y = unit.convert_unit(merged_global_Y, merged_length_unit, original_length_unit)
            # self.logger.printlog(f"    merged_global_X={merged_global_X} | merged_global_Y={merged_global_Y}")
            # self.logger.printlog(f"    original_global_X={original_global_X} | original_global_Y={original_global_Y}")

            deltaX_between_original_and_merged_storeys = merged_global_X - original_global_X
            deltaY_between_original_and_merged_storeys = merged_global_Y - original_global_Y
            if deltaX_between_original_and_merged_storeys or deltaY_between_original_and_merged_storeys:
                self.logger.printlog(f"    deltaX={deltaX_between_original_and_merged_storeys} | deltaY={deltaY_between_original_and_merged_storeys}")

            merged_rel_placements = merged_storey.ObjectPlacement.ReferencedByPlacements
            for rel_placement in merged_rel_placements:
                rel_placement.PlacementRelTo = storey_to_merge_into.ObjectPlacement
                if deltaX_between_original_and_merged_storeys or deltaY_between_original_and_merged_storeys:
                    new_point = self.file.create_entity(
                        "IfcCartesianPoint",
                        **{
                            "Coordinates": [
                                rel_placement.RelativePlacement.Location.Coordinates[0] + deltaX_between_original_and_merged_storeys, 
                                rel_placement.RelativePlacement.Location.Coordinates[1] + deltaY_between_original_and_merged_storeys, 
                                rel_placement.RelativePlacement.Location.Coordinates[2]
                                ]
                        },
                    )
                    new_3Dplacement = self.file.create_entity(
                        "IfcAxis2Placement3D",
                        **{
                            "Location": new_point,
                            "Axis": rel_placement.RelativePlacement.Axis,
                            "RefDirection": rel_placement.RelativePlacement.RefDirection,
                        },
                    )
                    rel_placement.RelativePlacement = new_3Dplacement
                    # Remove the old IfcCartesianPoint ? Need ot see if it is referenced somewhere else


    def purge_containers(self):
        for storey in self.file.by_type('IfcBuildingStorey'):
            self.remove_container_if_empty(storey)
            # if not storey.IsDecomposedBy and not storey.ContainsElements:
            #     self.file.remove(storey)
        for building in self.file.by_type('IfcBuilding'):
            self.remove_container_if_empty(building)
        for site in self.file.by_type('IfcSite'):
            if not hasattr(site, "Representation") or not site.Representation:
                self.remove_container_if_empty(site)

    def remove_container_if_empty(self, cont):
        if not cont.ContainsElements:
                if not cont.IsDecomposedBy:
                    self.file.remove(cont)
                else:
                    for rel_agg in cont.IsDecomposedBy:
                        if not rel_agg.RelatedObjects:
                            self.file.remove(rel_agg)
                    if not cont.IsDecomposedBy:
                        self.file.remove(cont)
        
    def manage_transfer_error(self, element):
        if element.is_a("IfcRelDefinesByType"):
            self.correct_type_transfer_error(element.RelatingType)
            self.file.add(element)
            self.logger.printlog("    Success")
            return True
        if element.is_a("IfcTypeProduct"):
            self.correct_type_transfer_error(element)
            self.file.add(element)
            self.logger.printlog("    Success")
            return True
        if element.is_a("IfcBuildingElementProxy"):
            self.correct_buildingelementproxy_transfer_error(element)
            self.file.add(element)
            self.logger.printlog("    Success")
            return True
        # if element.is_a("IfcBuildingElementProxyType"):
        #     for object_type_of in type.ObjectTypeOf:
        #         for rel_obj in object_type_of.RelatedObjects:
        #             self.correct_buildingelementproxy_transfer_error(rel_obj)
        #     self.file.add(element)
        #     self.logger.printlog("    Success")
        return False
    
    def correct_type_transfer_error(self, type):
        self.logger.printlog(f"    Error with Type #{type.id()}={type.is_a()} | Trying to set the PredefinedType as USERDEFINED then process")
        type.PredefinedType = "USERDEFINED"

        if type.is_a("IfcBuildingElementProxyType"):
            comp_type_values = {"ELEMENT", "COMPLEX", "PARTIAL"}
            for object_type_of in type.ObjectTypeOf:
                for rel_obj in object_type_of.RelatedObjects:
                    if rel_obj.CompositionType not in comp_type_values:
                        rel_obj.CompositionType = "ELEMENT"

    def correct_buildingelementproxy_transfer_error(self, element):
        self.logger.printlog(f"    Error with Element #{element.id()}={element.is_a()} | Trying to set the CompositionType as ELEMENT then process")
        comp_type_values = {"ELEMENT", "COMPLEX", "PARTIAL"}
        if element.CompositionType not in comp_type_values:
            element.CompositionType = "ELEMENT"

    def convert_length_units_of_all_elements(self, model, merged_unit, original_unit):
        classes_to_modify = {}
        s = ifcopenshell.ifcopenshell_wrapper.schema_by_name(model.schema)

        for d in s.declarations():
            if not hasattr(d, "all_attributes") :#or "IfcLength" not in str(d.all_attributes()):
                continue
            attributes_to_modify = []
            for attribute in d.all_attributes():
                if "IfcLength" in str(attribute):
                    attributes_to_modify.append(attribute.name())
            classes_to_modify[d.name()] = attributes_to_modify

        for ifc_class, attributes in classes_to_modify.items():
            for element in model.by_type(ifc_class):
                for attribute in attributes:
                    if element.is_a() != ifc_class:
                        self.logger.printlog(f"      Avoid converting units twice for class: {ifc_class} - (#{element.id()}={element.is_a()} | {attribute} | {getattr(element,attribute)})")
                        continue
                    value = getattr(element,attribute)
                    if value is None:
                        continue
                    if isinstance(value, tuple):
                        new_values = []
                        for val in value:
                            if isinstance(val,float):
                                new_values.append(unit.convert_unit(val, merged_unit, original_unit))
                            else:
                                new_values.append(val)
                        new_tuple = tuple(new_values)
                        setattr(element, attribute, new_tuple)
                    elif isinstance(value,float):
                        setattr(element, attribute, unit.convert_unit(getattr(element,attribute), merged_unit, original_unit))
                    else:
                        # self.logger.printlog(type(value))
                        continue

                    # self.logger.printlog(f"#{element.id()}={element.is_a()} | {attribute} | {getattr(element,attribute)}")
    
    def convert_length_units_in_properties(self, model, merged_unit, original_unit):
        for element in model.by_type("IfcPropertySingleValue"):
            if element.NominalValue and element.NominalValue.is_a("IfcLengthMeasure"):
                # self.logger.printlog(f"      {element.Name} | {element.NominalValue}")
                element.NominalValue.wrappedValue = unit.convert_unit(element.NominalValue.wrappedValue, merged_unit, original_unit)
        # Les quantités semblent déjà gérées

    def get_prj_units_dict(self, model):
        new_dict = {}
        unit_assignment = ifcopenshell.util.unit.get_unit_assignment(model)
        if unit_assignment:
            for unit in unit_assignment.Units or []:
                if unit.is_a("IfcNamedUnit"):
                    new_dict[unit.UnitType] = ifcopenshell.util.unit.get_project_unit(model, unit.UnitType)
        return new_dict
            
    def subtract_lists(self, main_list, subtract_list):
        new_list = []
        for element in main_list:
            if element not in subtract_list:
                new_list.append(element)
        return new_list
           
# file1_path = "./files/D2_ARC.ifc"
# file2_path = "./files/D2_CVP.ifc"
# f1 = ifcopenshell.open(file1_path)
# f2 = ifcopenshell.open(file2_path)

# my_patch = Patcher(f1, f2)
# my_patch.patch()

# f1.write('./output/test_patch_merge.ifc')