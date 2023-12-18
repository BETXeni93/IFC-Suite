import sys
import time
import ifcopenshell

# from ifcopenshell.api import run
import ifcopenshell.api

import ifcopenshell.util
import ifcopenshell.util.element
import ifcopenshell.util.unit
from logger import global_logger
import os
import ifcpatch_merge

import traceback

import tkinter as tk
from tkinter import filedialog

# import gc
# import psutil
# from pympler import asizeof

logging_every_element = 500
schema = ""
models_to_merge = []
models_name = []
parent_model = None

if getattr(sys, "frozen", False):
    dirpath = os.path.dirname(sys.executable)
elif __file__:
    dirpath = os.path.dirname(os.path.abspath(__file__))

files_folder = os.path.join(dirpath, "files")
output_folder = os.path.join(dirpath, "output")

models_to_open = ["D2_ARC.ifc","D2_CVP.ifc"]
output_filename = "INEX-merged.ifc"
output_filepath = os.path.join(output_folder, output_filename)

# global process
# process = psutil.Process(os.getpid())

def initiate_merge_environment(disable_logfile=False):
    global_logger.start_time = time.time()
    global_logger.disabled = disable_logfile
    global schema, models_to_merge, models_name
    schema = ""
    models_to_merge = []
    models_name = []
    return "success"


def process_cancelled():
    return os.path.exists(os.path.join(output_folder, "stop_flag.txt"))


def get_object_size(object):
    return "function deactivated"
    size = asizeof.asizeof(object)
    return f"size in bytes: {size:,}"


def print_memory():
    return
    global process
    memory_use = process.memory_info().rss
    global_logger.printlog(f"Memory used: {memory_use:,} bytes")


# get_models_from_contents --- Cannot parse IFCZIP
def get_model_from_contents(name, content):
    global schema, models_to_merge, models_name
    # global_logger.printlog("Script starts: Getting files from txt content")
    # global_logger.printlog("...")
    if not content: # schema returns "" when the model is not correctly loaded (too big file?)
        global_logger.printlog(f"ERROR : Model couldn't be loaded (content is empty) (file might be too big)")
        return "error", "Model couldn't be loaded (content is empty) (file might be too big)"
    global_logger.printlog(f'Getting model from content: {name} ...')
    model = ifcopenshell.file.from_string(content)
    # if not model.schema: # schema returns "" when the model is not correctly loaded (too big file?)
    #     global_logger.printlog(f"ERROR : Model couldn't be loaded")
    #     return "cancelled"
    if model.schema != schema and schema != "":
        error_message = f"Unable to merge models with different IFC schemas ({schema} and {model.schema})"
        global_logger.printlog(error_message)
        return "error", error_message
    schema = model.schema
    models_name.append(name)
    models_to_merge.append(model)
    if process_cancelled():
        return "error", "Process was cancelled by the user"
    global_logger.printlog("Done")
    global_logger.printlog()
    return "success", ""

def patch_merge(model_num, merge_sites=True, merge_buildings=True, lvls_mgmt=0, remove_empty_containers=True):
    global parent_model
    parent_model = models_to_merge[0]
    child_model = models_to_merge[model_num]
    global_logger.printlog(f"Start merge: <{models_name[model_num]}> into <{models_name[0]}>") 
    global_logger.printlog()

    merger = ifcpatch_merge.Merger(
        parent_model, 
        child_model,
        merge_sites=merge_sites,
        merge_buildings=merge_buildings,
        lvls_mgmt=lvls_mgmt,
        remove_empty_containers=remove_empty_containers
        )
    parent_model = merger.merge()

    global_logger.printlog()
    global_logger.printlog("Merge done")
    global_logger.printlog()
    global_logger.printlog()
    return "success"

def prompt_output_filename():
    try:
        root = tk.Tk()
        root.withdraw()  # Cache la fenêtre principale
        path = filedialog.asksaveasfilename(
            title="Select output directory", 
            defaultextension=".ifc", 
            filetypes=[("IFC files", ".ifc")], 
            initialfile="INEX-merged.ifc")
        root.destroy()  # Destroy the main application window
        root.quit()
        root.mainloop()
        return "success", path
    except Exception as ex:
        global_logger.printlog(f"An error occured: {ex}")
        global_logger.printlog(traceback.format_exc())
        return "error", ex

def save_merged_file(path):
    try:
        if path == "":
            global_logger.printlog("Invalid output directory")
            return "cancel"
        global_logger.printlog(path)
        parent_model.write(path)
        global_logger.printlog("Done")
        global_logger.printlog()
        global_logger.printlog(
            "---------------------------------------------------")
        global_logger.printlog()
        global_logger.printlog(
            f"Merged model was successfully saved to <{path}>")
        return "success"
    except Exception as erreur:
        global_logger.printlog(
            "-----------------------------------------------")
        global_logger.printlog(f"An error occured: {erreur}")
        global_logger.printlog(traceback.format_exc())
        global_logger.printlog(
            "-----------------------------------------------")
        return "error"


def get_prj_units_dict(model):
    new_dict = {}
    unit_assignment = ifcopenshell.util.unit.get_unit_assignment(model)
    if unit_assignment:
        for unit in unit_assignment.Units or []:
            if unit.is_a("IfcNamedUnit"):
                new_dict[unit.UnitType] = ifcopenshell.util.unit.get_project_unit(
                    model, unit.UnitType)
    return new_dict


def open_and_get_models(files_folder, models_to_open):
    global models_to_merge, models_name
    global_logger.printlog("Script starts: Opening files")

    for model_to_open in models_to_open:
        print_memory()
        model_name = os.path.basename(model_to_open)
        global_logger.printlog(f"Opening file: {model_name} ...")
        model_path = os.path.join(files_folder, model_to_open)
        if os.path.exists(model_path):
            models_to_merge.append(ifcopenshell.open(model_path))
            models_name.append(model_name)
            # global_logger.printlog("Size of models: " + get_object_size(models))
            # global_logger.printlog(gc.get_referrers(models[-1]))
            global_logger.printlog(
                f"Model <{model_name}> [{models_to_merge[-1].schema}] was successfully opened"
            )
        else:
            global_logger.printlog(
                f"Error : File <{model_path}> doesn't exist"
            )
        print_memory()
    global_logger.printlog("All files are opened")
    global_logger.printlog()


def main():
    initiate_merge_environment()
    global_logger.initiate_logfile(output_folder)
    # print_memory()
    open_and_get_models(files_folder, models_to_open)
    # print_memory()
    # merge_models(lvls_mgmt=0, separate_buildings=True)
    for model_num in range(1, len(models_to_merge)):
        patch_merge(model_num)
    global_logger.printlog()
    global_logger.printlog(
        "---------------------------------------------------")
    global_logger.printlog()
    global_logger.printlog(
        f"Merge done, saving file to <{output_filepath}>"
    )
    global_logger.printlog("...")
    save_merged_file(output_filepath)
    # print_memory()
    global_logger.close_log_file()
    # print_memory()


if __name__ == "__main__":
    main()
