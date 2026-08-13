import yaml
import sys
import os

def update_workspace_config(feature_name):
    """Update the workspace configuration with the new feature branch name."""
    new_workspace_name = f'fuam_feature_branch_{feature_name}'
    config_file = 'config/item_src_config.yaml'
    
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
    if len(sys.argv) != 2:
        print("Usage: python update_workspace.py <feature_name>")
        sys.exit(1)
    
    feature_name = sys.argv[1]
    success = update_workspace_config(feature_name)
    
    if not success:
        sys.exit(1)
