import argparse
import yaml
from pathlib import Path

def update_workspace_config(feature_name, module_id):
    """Update the workspace configuration with the new feature branch name."""
    new_workspace_name = f'fos_feature_branch_{feature_name}'
    config_file = Path('cicd') / 'modules' / module_id / 'item_src_config.yaml'
    
    print(f'Updating workspace to: {new_workspace_name}')
    
    try:
        # Read the YAML file
        with open(config_file, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        
        print(f'Original workspace: {config.get("workspace", "Not found")}')
        
        # Update the workspace value
        config['workspace'] = new_workspace_name
        
        # Write back to file
        with open(config_file, 'w', encoding='utf-8') as file:
            yaml.dump(config, file, default_flow_style=False, allow_unicode=True)
        
        print(f'Updated workspace to: {new_workspace_name}')
        
        # Verify the change
        with open(config_file, 'r', encoding='utf-8') as file:
            updated_config = yaml.safe_load(file)
        print(f'Verified workspace: {updated_config.get("workspace", "Not found")}')
        
        return True
        
    except Exception as e:
        print(f'Error updating workspace config: {e}')
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update a module development workspace")
    parser.add_argument("feature_name")
    parser.add_argument("--module", required=True)
    args = parser.parse_args()
    success = update_workspace_config(args.feature_name, args.module)

    if not success:
        raise SystemExit(1)
