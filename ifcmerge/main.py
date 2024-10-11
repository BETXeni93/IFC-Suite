import sys
import time
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util
import ifcopenshell.util.element
import ifcopenshell.util.unit
import logger
import os
import ifcpatch_merge

import traceback

import tkinter as tk
from tkinter import filedialog

import psutil
# from pympler import asizeof


class Main:
    def __init__(self):
        self.logging_every_element = 500
        self.schema = ""
        self.models_to_merge = []
        self.models_name = []
        self.parent_model = None
        self.logger = None

        if getattr(sys, "frozen", False):
            dirpath = os.path.dirname(sys.executable)
        elif __file__:
            dirpath = os.path.dirname(os.path.abspath(__file__))

        self.files_folder = os.path.join(dirpath, "files")
        self.output_folder = os.path.join(dirpath, "output")

        self.models_to_open = ["ARC.ifc", "CVP.ifc"]
        self.output_filename = "IFCSuite_merged.ifc"
        self.output_filepath = os.path.join(self.output_folder, self.output_filename)

        self.process = psutil.Process(os.getpid())

    def initiate_merge_environment(self, disable_log=False):
        self.logger = logger.Logger()
        self.logger.start_time = time.time()
        self.logger.no_output_file = True
        self.logger.disabled = disable_log
        self.print_memory()
        global schema, models_to_merge, models_name
        schema = ""
        models_to_merge = []
        models_name = []
        return "success"

    def get_object_size(object):
        return "function deactivated"
        size = asizeof.asizeof(object)
        return f"size in bytes: {size:,}"

    def print_memory(self):
        return
        memory_use = self.process.memory_info().rss
        self.logger.printlog(f"Memory used: {memory_use:,} bytes")

    # get_models_from_contents --- Cannot parse IFCZIP
        
    def save_input_files(self, model_name, model_file, input_folder):
        self.logger.printlog("Script starts: Saving input files")
        self.logger.printlog("...")
        if not os.path.exists(input_folder):
            os.makedirs(input_folder)
        model_path = os.path.join(input_folder, model_name)
        with open(model_path, "wb") as f:
            f.write(model_file)
        self.logger.printlog(f"File <{model_name}> was successfully saved")
        self.logger.printlog()
        return "success"

    def get_model_from_contents(self, name, content):
        # schema returns "" when the model is not correctly loaded (too big file?)
        if not content:
            self.logger.printlog(f"ERROR : Model couldn't be loaded (content is empty) (file might be too big)")
            return "error", "Model couldn't be loaded (content is empty) (file might be too big)"
        self.logger.printlog(f'Getting model from content: {name} ...')
        try:
            model = ifcopenshell.file.from_string(content)
        except Exception as ex:
            self.logger.printlog(f"An error occured: {ex}")
            self.logger.printlog(traceback.format_exc())
            return "error", ex
        if model.schema != self.schema and self.schema != "":
            error_message = f"Unable to merge models with different IFC schemas ({self.schema} and {model.schema})"
            self.logger.printlog(error_message)
            return "error", error_message
        self.schema = model.schema
        self.models_name.append(name)
        self.models_to_merge.append(model)
        self.logger.printlog("Done")
        self.logger.printlog()
        return "success", ""

    def free_memory(self):
        self.logger.printlog("Freeing memory")
        self.print_memory()
        global models_to_merge, parent_model
        models_to_merge = []
        self.logger.printlog("Done freeing memory")
        self.print_memory()

    def patch_merge(self, model_num, merge_sites=True, merge_buildings=True, lvls_mgmt=0, remove_empty_containers=True):
        self.parent_model = self.models_to_merge[0]
        child_model = self.models_to_merge[model_num]
        self.print_memory()
        self.logger.printlog(f"Start merge: <{self.models_name[model_num]}> into <{self.models_name[0]}>")
        self.logger.printlog()

        merger = ifcpatch_merge.Merger(
            self.logger,
            self.parent_model,
            child_model,
            merge_sites=merge_sites,
            merge_buildings=merge_buildings,
            lvls_mgmt=lvls_mgmt,
            remove_empty_containers=remove_empty_containers
        )
        self.parent_model = merger.merge()
        self.print_memory()

        self.logger.printlog()
        self.logger.printlog("Merge done")
        self.logger.printlog()
        self.logger.printlog()
        return "success", ""

    def prompt_output_filename(self):
        try:
            root = tk.Tk()
            root.withdraw()  # Hides main window
            path = filedialog.asksaveasfilename(
                title="Select output directory",
                defaultextension=".ifc",
                filetypes=[("IFC files", ".ifc")],
                initialfile=self.output_filename)
            root.destroy()  # Destroy the main application window
            root.quit()
            root.mainloop()
            return "success", path
        except Exception as ex:
            self.logger.printlog(f"An error occured: {ex}")
            self.logger.printlog(traceback.format_exc())
            return "error", ex

    def save_merged_file(self, path):
        try:
            if path == "":
                self.logger.printlog("Invalid output directory")
                return "cancel"
            self.logger.printlog(path)
            self.parent_model.write(path)
            self.logger.printlog("Done")
            self.logger.printlog()
            self.logger.printlog(
                "---------------------------------------------------")
            self.logger.printlog()
            self.logger.printlog(
                f"Merged model was successfully saved to <{path}>")
            return "success"
        except Exception as erreur:
            self.logger.printlog(
                "-----------------------------------------------")
            self.logger.printlog(f"An error occured: {erreur}")
            self.logger.printlog(traceback.format_exc())
            self.logger.printlog(
                "-----------------------------------------------")
            return "error"

    def get_prj_units_dict(self, model):
        new_dict = {}
        unit_assignment = ifcopenshell.util.unit.get_unit_assignment(model)
        if unit_assignment:
            for unit in unit_assignment.Units or []:
                if unit.is_a("IfcNamedUnit"):
                    new_dict[unit.UnitType] = ifcopenshell.util.unit.get_project_unit(
                        model, unit.UnitType)
        return new_dict


    def open_and_get_models(self, files_folder, models_to_open):
        self.logger.printlog("Script starts: Opening files")

        for model_to_open in models_to_open:
            self.print_memory()
            model_name = os.path.basename(model_to_open)
            self.logger.printlog(f"Opening file: {model_name} ...")
            model_path = os.path.join(files_folder, model_to_open)
            if os.path.exists(model_path):
                self.models_to_merge.append(ifcopenshell.open(model_path))
                self.models_name.append(model_name)
                # self.logger.printlog("Size of models: " + get_object_size(models))
                # self.logger.printlog(gc.get_referrers(models[-1]))
                self.logger.printlog(
                    f"Model <{model_name}> [{self.models_to_merge[-1].schema}] was successfully opened"
                )
            else:
                self.logger.printlog(
                    f"Error : File <{model_path}> doesn't exist"
                )
            self.print_memory()
        self.logger.printlog("All files are opened")
        self.logger.printlog()

    def main(self):
        self.initiate_merge_environment(disable_log=False)
        # self.print_memory()
        self.open_and_get_models(self.files_folder, self.models_to_open)
        # self.print_memory()
        for model_num in range(1, len(self.models_to_merge)):
            self.patch_merge(model_num)
        self.logger.printlog()
        self.logger.printlog("---------------------------------------------------")
        self.logger.printlog()
        self.logger.printlog(f"Merge done, saving file to <{self.output_filepath}>")
        self.logger.printlog("...")
        self.save_merged_file(self.output_filepath)
        # self.print_memory()
        self.logger.close_log_file()
        # self.print_memory()

if __name__ == "__main__":
    main_inst = Main()
    main_inst.main()
