# FOS Update

To update FOS (Fabric Unified Admin Monitoring) to the latest version, follow the documented steps below.

![FOS update process overview](/monitoring/fabric-unified-admin-monitoring/media/deployment/update_fos_process_cover.png)

**Important:**

- FOS updates **overwrite all FOS-provided items** based on the item name.
- FOS updates **do not** affect your collected data within the `FOS_Lakehouse`; only the metadata will be overwritten.
- If you **have made custom changes to pipelines, notebooks, semantic models, and reports**, please **create a backup or rename your custom items**.
- **Recommended:** Take a screenshot of your current pipeline parameters in `Load_FOS_Data_E2E` before the update.
- **Recommended:** Back up your workspace items (e.g., using Git) before the update.
- **Recommended:** Check the release notes of FOS to see enhanced, fixed, or new items and features.
- **Use the same user to update FOS** as you **used during initial deployment**. It is important to do so because this user is the owner of all the FOS-related items and the cloud connections.

## Lakehouse schema migration

The current release consolidates Admin Monitoring storage into the schema-enabled `FOS_Lakehouse`:

- Persistent Admin Monitoring tables move to `admin`.
- Tables whose names contain `metrics` move to `capacity_metrics`.
- Intermediate tables move from `FOS_Staging_Lakehouse` to `staging`.
- Deployment metadata moves from `FOS_Config_Lakehouse` to `config`.
- `FOS_Staging_Lakehouse`, `FOS_Config_Lakehouse`, and `FOS_Backup_Lakehouse` are no longer deployed.
- `01_FOS_Lakehouse_Backup` is removed, and `Maintenance_for_FOS` now performs table optimization only.

Fabric can't currently convert an existing non-schema Lakehouse in place. Existing installations must provision a schema-enabled `FOS_Lakehouse` and migrate retained data into the schemas above before running the updated deployment. Back up any required historical data externally before removing legacy Lakehouses.

# Steps

## 1. Preparation

**Optional:** Review the [changelog here](/monitoring/fabric-unified-admin-monitoring/changelog/FOS_Changelog.md).

#### 1a) Scope of the update
Before you update your FOS workspace, please review the following illustration, which describes which items will be overwritten or updated during an update of FOS:

![FOS update process scope](/monitoring/fabric-unified-admin-monitoring/media/deployment/update_fos_process_scope.png)

**Important:** Other items with custom names won't be affected by the update.

#### 1b) Before you update

1. (Recommended) **Back up your workspace** items (e.g., using Git) before the update.
2. (Recommended) **Check the release notes** of FOS to see enhanced, fixed, or new items and features.
3. (Recommended) **Take a screenshot** of your current pipeline parameters in `Load_FOS_Data_E2E` before the update.
4. (Highly recommended) **Use the same user to update FOS** as you **used during initial deployment**. It is important to do so because this user is the owner of all the FOS-related items and the cloud connections.
 
## 2. Download and run Notebook

1. **Download** the latest version of the [Deploy_FOS.ipynb](/monitoring/fabric-unified-admin-monitoring/scripts/Deploy_FOS.ipynb) notebook.
2. **Remove** the old `Deploy_FOS` notebook from your workspace.
3. **Import** the updated notebook into your FOS workspace.
4. **Run** the `Deploy_FOS.ipynb` notebook from within your FOS workspace.

    ![](/monitoring/fabric-unified-admin-monitoring/media/deployment/FOS_basic_deployment_process_3_2.png)

> **Info:** This notebook is designed to initially deploy or update all the items in your FOS workspace.

## 3. Update Pipeline parameters

**Important:** When you re-run the `Deploy_FOS` notebook, the update logic will overwrite your current parameters in the `Load_FOS_Data_E2E` pipeline.

5. Open the `Load_FOS_Data_E2E` pipeline in your FOS workspace.
6. Set your previously saved parameters.
7. Save the pipeline.

## 4. Open PBI report

8. Navigate to your FOS workspace.
9. Search for the item `FOS_Core_Report`.
10. Open the `FOS_Core_Report` Power BI report.
11. Feel free to explore the report pages:
    ![](/monitoring/fabric-unified-admin-monitoring/media/deployment/FOS_basic_deployment_process_7_3.png)

12. (Optional - only if needed) **Reconfigure** semantic model parameters of:
    - `FOS_Semantic_Model_Meta_Data_Analyzer_SM`
    - `FOS_SQL_Endpoint_Analyzer_Report_SM`
    - `FOS_Gateway_Monitoring_Report_From_Files_SM`

**Info:**  
You do **not** need to manually run the `Load_FOS_Data_E2E` pipeline after an update. 
**During the next pipeline run**, FOS will also check and update the status of your FOS version on the first page of the `FOS_Core_Report`:

![](/monitoring/fabric-unified-admin-monitoring/media/deployment/updated_fos_status.png)


## Congratulations!

You are now using the latest and greatest version of FOS!

----------------

## Other helpful resources
- [Video - Brief introduction to FOS](https://youtu.be/CmHMOsQcMGI)
- [Documentation - FOS Authorization & Authentication](/monitoring/fabric-unified-admin-monitoring/media/documentation/FOS_Authorization.md)
- [Documentation - FOS Architecture](/monitoring/fabric-unified-admin-monitoring/media/documentation/FOS_Architecture.md)
- [Documentation - FOS Lakehouse Table Lineage](/monitoring/fabric-unified-admin-monitoring/media/documentation/FOS_Documentation_Lakehouse_table_lineage.pdf)
- [Documentation - FOS Technical Deep Dive](/monitoring/fabric-unified-admin-monitoring/media/documentation/FOS_Technical_Deep_Dive.md)
