import argparse
import uuid
import os
import json
import shutil
import re
import subprocess
import hashlib
import stat, errno
import yaml

parser = argparse.ArgumentParser(description="Export one FOS module from Fabric")
parser.add_argument("--module", required=True, help="Module ID under cicd/modules")
args = parser.parse_args()

module_id = args.module
if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", module_id):
    parser.error("--module must be a lowercase kebab-case identifier")

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
module_cicd_dir = os.path.join(base_path, 'cicd', 'modules', module_id)
config_dir = os.path.join(base_path, 'config', 'modules', module_id)
config_path = os.path.join(module_cicd_dir, 'item_src_config.yaml')

if not os.path.isfile(config_path):
    parser.error(f"module configuration not found: {config_path}")

with open(config_path, 'r') as file:
        config = yaml.safe_load(file)

#print(config)

perform_export = True

deployment_workspace_name = "FOS"
src_workspace_name = config['workspace']
src_pbi_connection = config['connections']['pbi_connection']
src_fabric_connection = config['connections']['fabric_connection']
items = config['items']
#items = ['FOS_Lakehouse.Lakehouse', 'FOS_Staging_Lakehouse.Lakehouse', 'Generate_Calendar_Table.Notebook']
item_inventory = []

namespace = uuid.NAMESPACE_DNS
prefix = "FOS"

print("Start FOS Get Resources Script")

##################################################################################################


def run_fab_command( command, capture_output: bool = False, silently_continue: bool = False
):
    print(f"Running fab command: {command}")

    result = subprocess.run(["fab", "-c", command], capture_output=capture_output, text=True)

    if (not(silently_continue) and (result.returncode > 0 or result.stderr)):
        raise Exception(f"Error running fab command. exit_code: '{result.returncode}'; stderr: '{result.stderr}'")    

    if (capture_output): 
        output = result.stdout.strip()
        return output
    
##################################################################################################



def add_item_to_inventory(item_name, item_id, guids=[]):
    fos_id = str(uuid.uuid3(namespace, prefix + item_name))
    item_def = { "name": item_name, "original_id": item_id, "fos_id": fos_id, "related_items" : guids }
    item_inventory.append(item_def)

def handleRemoveReadonly(func, path, exc):
  excvalue = exc[1]
  if func in (os.rmdir, os.remove) and excvalue.errno == errno.EACCES:
      os.chmod(path, stat.S_IRWXU| stat.S_IRWXG| stat.S_IRWXO) # 0777
      func(path)
  else:
      raise
  
def extract_guids(file_content, file_extension):
    """
    Extracts unique GUIDs from the given file content.
    Args:  
        file_content (str): The content of the file.
        file_extension (str): The extension of the file.
    Returns:  
        list: A list of unique GUIDs.   
    """
    if file_extension == '.ipynb':
        try:
            notebook_json = json.loads(file_content)
            dependencies = notebook_json.get('metadata', {}).get('dependencies', {})
            guids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', str(dependencies))
        except json.JSONDecodeError:
            guids = []
    else:
        guids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', file_content)
    
    unique_guids = set(guids)
    unique_guids.discard('00000000-0000-0000-0000-000000000000')
    return list(unique_guids)

##############################################

def process_file(path):
    """
    Processes files in the given base path to extract logical IDs and GUIDs.
    Args:
        base_path (str): The base directory path.
        item_inventory (list): List of dictionaries containing item information.
    Returns:
        dict: A dictionary containing processed items and a set of all found GUIDs.
    """
    
    guids = []
    for root, dirs, files in os.walk(path):
        
            for file in files:
                if file.endswith(('.py', '.json', '.pbir', '.platform', '.ipynb')) and not file.endswith('report.json'):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r',encoding="utf8") as f:
                        file_content = f.read()
                    
                        guids = extract_guids(file_content, os.path.splitext(file)[1])
    # sort guids to have a consistent order
    guids = sorted(set(guids))
    return guids




#######################################################################################################
src_workspace_id = run_fab_command(f"get {src_workspace_name}.Workspace -q id", silently_continue=True, capture_output=True)
print("Workspace ID:", src_workspace_id)
add_item_to_inventory(f"{deployment_workspace_name}.Workspace" , src_workspace_id, [])
src_pbi_connection_id = run_fab_command(f"get .connections/{src_pbi_connection}.Connection -q id", silently_continue=True, capture_output=True)
print("PBI Connection ID:", src_pbi_connection_id)
add_item_to_inventory(src_pbi_connection, src_pbi_connection_id, [])
src_fabric_connection_id = run_fab_command(f"get .connections/{src_fabric_connection}.Connection -q id", silently_continue=True, capture_output=True)
print("Fabric Connection ID:", src_fabric_connection_id, [])
add_item_to_inventory(src_fabric_connection, src_fabric_connection_id)

#######################################################################################################
tmp_path = os.path.join(base_path, "tmp", module_id)
# check if tmp folder exists, if yes delete it
if os.path.exists(tmp_path) and perform_export:
    shutil.rmtree(tmp_path, onerror=handleRemoveReadonly)

os.makedirs(tmp_path, exist_ok=True)
all_guids = set()

for item in items:
    print(item)
    guids = []
    item_id = run_fab_command(f"get {src_workspace_name}.Workspace/{item} -q id", silently_continue=True, capture_output=True)
    if not item.endswith('.Lakehouse') and not item.endswith(".Environment"):
        if perform_export:
            run_fab_command(  f"export {src_workspace_name}.Workspace/{item} -o {tmp_path} -f ", silently_continue=False)
        guids = process_file(os.path.join(tmp_path, item))
        add_item_to_inventory(item, item_id, guids)
        all_guids.update(guids)

    else:
        add_item_to_inventory(item, item_id, [])

print(item_inventory)

    
missing_guids = []
print_yel = '\033[93m'     
print_white = '\033[0m' 
for guid in all_guids:
    found = any(guid in item["original_id"] for item in item_inventory)
    if not found:
        missing_guids.append(guid)
        print(f"{print_yel}GUID not found in item inventory:", guid, print_white) 

if missing_guids:
    print("Missing GUIDs:", missing_guids)
else:
    print("All GUIDs found in item inventory.")



# Copy all files in item_inventory from tmp to src folder, replace all the original ids with fos ids
src = tmp_path
dst = os.path.join(base_path, 'src', 'modules', module_id)
if not os.path.exists(dst):
    os.makedirs(dst)

deployment_order_new = []

if os.path.exists(dst):
    shutil.rmtree(dst, onerror=handleRemoveReadonly)
    os.makedirs(dst, exist_ok=True)

for item in item_inventory:
    folder_name = item['name']
    folder_path = os.path.join(src, folder_name)
    if os.path.exists(folder_path):
        new_folder_path = os.path.join(dst, folder_name)
        shutil.copytree(folder_path, new_folder_path, dirs_exist_ok=True)
        for root, dirs, files in os.walk(new_folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                 # Read and process the file content
                if os.path.isfile(file_path):
                    if ".png" in file_path.lower():
                        with open(file_path, 'rb') as f:
                            file_content = f.read()
                            with open(file_path, 'wb') as f:
                                f.write(file_content)
                    else:
                        with open(file_path, 'r', encoding="utf8") as f:
                            file_content = f.read()
                        for it in item_inventory:
                            file_content = file_content.replace(it['original_id'], it['fos_id'])
                        
                        # Handle .ipynb files specifically to clean cellStatus in metadata
                        if file.endswith('.ipynb'):
                            try:
                                # Parse as JSON to handle notebook structure
                                notebook_json = json.loads(file_content)
                                
                                # Clean cellStatus from cell metadata
                                if 'cells' in notebook_json:
                                    for cell in notebook_json['cells']:
                                        if 'metadata' in cell and 'cellStatus' in cell['metadata']:
                                            cell['metadata']['cellStatus'] = ""
                                            cell['execution_count'] = None
                                        
                                if 'metadata' in notebook_json:
                                    if 'synapse_widget' in notebook_json['metadata']:
                                        notebook_json['metadata'].pop('synapse_widget', None)



                                # Convert back to JSON string
                                file_content = json.dumps(notebook_json, indent=2)
                            except json.JSONDecodeError:
                                print("Ipynb processing failed, file might not be valid JSON")
                                # If it's not valid JSON, treat as regular text (XML format)
                                # Use regex to find and replace cellStatus content in XML

                        
                        with open(file_path, 'w', encoding="utf8") as f:
                            f.write(file_content)

    deployment_order_new.append({'name': folder_name, 'fos_id': item['fos_id']})

# Write the deployment order to a JSON file
deployment_order_new_path = os.path.join(config_dir, 'deployment_order.json')
with open(deployment_order_new_path, 'w') as json_file:
    json.dump(deployment_order_new, json_file, indent=4)

print(f"Deployment order written to {deployment_order_new_path}")

shutil.rmtree(tmp_path, onerror=handleRemoveReadonly)


