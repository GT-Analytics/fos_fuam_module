# FUAM Resource Update Workflow

This repository contains a GitHub Actions workflow that automatically updates the FUAM resources by executing the `fuam_get_ressources.py` script.

## 🚀 Workflow Overview

The workflow (`update-resources.yml`) performs the following actions:

1. **Exports resources** from the source Microsoft Fabric workspace
2. **Processes and transforms** the exported files
3. **Updates** the `src/` and `config/` folders in the repository
4. **Commits changes** back to the repository

## 📋 Prerequisites

Before using this workflow, you need to set up the following repository secrets:

### Required Secrets

Navigate to your repository → Settings → Secrets and variables → Actions, and add:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `AZURE_TENANT_ID` | Your Azure AD tenant ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `AZURE_CLIENT_ID` | Service Principal client ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `AZURE_CLIENT_SECRET` | Service Principal client secret | `your-client-secret` |

### Setting Up Service Principal

1. **Create a Service Principal** in Azure AD:
   ```bash
   az ad sp create-for-rbac --name "fuam-github-actions" --role contributor
   ```

2. **Grant Fabric permissions** to the Service Principal:
   - Add the Service Principal to your Fabric workspace
   - Assign appropriate permissions (Admin or Member)

3. **Note down the credentials** from the command output

## 🔧 Workflow Triggers

The workflow runs automatically in the following scenarios:

### 1. Manual Trigger
```bash
# You can manually trigger the workflow from GitHub Actions tab
```

### 2. Scheduled Runs
- **Every Monday at 6 AM UTC** (configurable in the workflow)

### 3. Configuration Changes
Triggers when changes are made to:
- `config/item_src_config.yaml`
- `config/deployment_config.yaml` 
- `scripts/fuam_get_ressources.py`

## 📁 What Gets Updated

### Source Folder (`src/`)
- Contains exported Fabric items (Notebooks, Lakehouses, etc.)
- Original IDs replaced with FUAM IDs for consistency
- Cleaned metadata (e.g., cellStatus in notebooks)

### Configuration Files
- `config/item_inventory.json` - Mapping of original IDs to FUAM IDs
- `config/deployment_order.json` - Deployment sequence for items

## 🔍 Workflow Steps

1. **Setup Environment**
   - Checkout repository
   - Install Python and dependencies
   - Install Microsoft Fabric CLI

2. **Authentication**
   - Login to Microsoft Fabric using Service Principal

3. **Resource Processing**
   - Execute `fuam_get_ressources.py`
   - Export and process Fabric items
   - Generate updated configurations

4. **Commit Changes**
   - Check for modifications
   - Commit updates with descriptive message
   - Push to main branch (or create PR if on feature branch)

## 🛠️ Customization

### Modify Schedule
Edit the cron expression in the workflow:
```yaml
schedule:
  - cron: '0 6 * * 1'  # Currently: Every Monday at 6 AM UTC
```

### Add Dependencies
If your script requires additional Python packages:
```yaml
- name: Install Python dependencies
  run: |
    pip install pyyaml requests pandas  # Add your packages here
```

### Environment Variables
Add environment variables in the workflow if needed:
```yaml
env:
  CUSTOM_VAR: ${{ secrets.CUSTOM_SECRET }}
```

## 📊 Monitoring

### GitHub Actions Tab
- View workflow execution history
- Check logs for troubleshooting
- Monitor success/failure rates

### Workflow Summary
Each run generates a summary showing:
- Execution timestamp
- Whether changes were detected
- List of updated files

## 🚨 Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify service principal credentials
   - Check Fabric workspace permissions
   - Ensure secrets are correctly set

2. **Script Errors**
   - Check Python dependencies
   - Verify configuration file formats
   - Review workspace and item names

3. **Permission Issues**
   - Ensure GitHub token has write permissions
   - Check repository settings for Actions

### Debug Mode
To enable verbose logging, add this to your workflow:
```yaml
env:
  ACTIONS_STEP_DEBUG: true
```

## 📞 Support

For issues with:
- **Workflow**: Check GitHub Actions logs and this documentation
- **Script logic**: Review `fuam_get_ressources.py` and related configuration files
- **Fabric integration**: Verify workspace permissions and item accessibility

---

*This workflow helps maintain synchronization between your Microsoft Fabric workspace and this Git repository, ensuring your deployment artifacts are always up to date.*
