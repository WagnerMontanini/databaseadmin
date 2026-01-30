/////////////////////////////////////////////////////////////
//
// pgAdmin 4 - PostgreSQL Tools
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import { getNodeListByName, getNodeAjaxOptions } from '../../../../browser/static/js/node_ajax';
import SqlExportSchema from './sql_export.ui';
import getApiInstance from 'sources/api_instance';
import { retrieveAncestorOfTypeServer } from 'sources/tree/tree_utils';
import pgAdmin from 'sources/pgadmin';
import { AllPermissionTypes } from '../../../../browser/static/js/constants';

define([
  'sources/gettext', 'sources/url_for', 'pgadmin.browser',
  'tools/backup/static/js/menu_utils',
  'sources/nodes/supported_database_node',
], function (
  gettext, url_for, pgBrowser, menuUtils, supportedNodes
) {
  if (pgBrowser.SqlExport) {
    return pgBrowser.SqlExport;
  }

  pgBrowser.SqlExport = {
    init: function () {
      if (this.initialized) return;
      this.initialized = true;

      // Mostrar no contexto de database (e também em tools menu se quiser expandir)
      let menus = [{
        name: 'sql_export_database_ctx',
        module: this,
        node: 'database',
        applies: ['context'],
        callback: 'exportSql',
        priority: 3,
        label: gettext('Export database as SQL...'),
        icon: 'fa fa-download',
        enable: supportedNodes.enabled.bind(
          null, pgBrowser.tree, menuUtils.backupSupportedNodes
        ),
        permission: AllPermissionTypes.TOOLS_BACKUP,
      }];

      pgBrowser.add_menus(menus);
      return this;
    },

    exportSql: function (_action, treeItem) {
      let tree = pgBrowser.tree,
        i = treeItem || tree.selected(),
        data = i ? tree.itemData(i) : undefined;

      const serverInformation = retrieveAncestorOfTypeServer(
        pgBrowser, treeItem, gettext('SQL Export Error')
      );
      const sid = serverInformation._type == 'database' ? serverInformation._pid : serverInformation._id;
      const did = data._id;

      const api = getApiInstance();
      const utility_exists_url = url_for('sql_export.utility_exists', { sid: sid });

      return api({ url: utility_exists_url, method: 'GET' }).then((res) => {
        // Aqui, se psql não existir ainda, retornamos erro (para server output)
        if (!res.data.success) {
          pgAdmin.Browser.notifier.alert(
            gettext('Utility not found'),
            gettext(res.data.errormsg)
          );
          return;
        }

        const objectsUrl = url_for('backup.objects', { sid: sid, did: did });
        const schema = this.getUISchema(treeItem, sid, did, objectsUrl);
        const extraData = this.setExtraParameters(treeItem, sid, did);

        const urlBase = url_for('sql_export.create_job', { sid: sid });
        const helpUrl = url_for('help.static', { filename: 'backup_dialog.html' });

        pgAdmin.Browser.Events.trigger('pgadmin:utility:show', treeItem,
          gettext(`Export SQL (${data.label})`),
          { schema, extraData, urlBase, helpUrl, saveBtnName: gettext('Export') },
          pgAdmin.Browser.stdW.md, pgAdmin.Browser.stdH.lg
        );
      });
    },

    getUISchema: function (treeItem, sid, did, objectsUrl) {
      let treeNodeInfo = pgBrowser.tree.getTreeNodeHierarchy(treeItem);
      const selectedNode = pgBrowser.tree.selected();
      let itemNodeData = pgBrowser.tree.findNodeByDomElement(selectedNode).getData();

      return new SqlExportSchema(
        {
          role: () => getNodeListByName('role', treeNodeInfo, itemNodeData),
          encoding: () => getNodeAjaxOptions('get_encodings', pgBrowser.Nodes['database'], treeNodeInfo, itemNodeData, {
            cacheNode: 'database',
            cacheLevel: 'server',
          }),
          targetServers: () => {
            // Reaproveitar endpoint do Query Tool que lista servers
            return new Promise((resolve, reject) => {
              const api = getApiInstance();
              api({
                url: url_for('sqleditor.get_new_connection_servers'),
                method: 'GET',
              }).then((resp) => {
                const serverGroupData = resp.data?.data?.result?.server_list || {};
                const options = [];
                Object.keys(serverGroupData).forEach((grp) => {
                  serverGroupData[grp].forEach((s) => {
                    options.push({
                      label: `${s.label} (${grp})`,
                      value: s.value,
                    });
                  });
                });
                resolve(options);
              }).catch((err) => reject(err));
            });
          },
        },
        treeNodeInfo,
        pgBrowser,
        {
          objects: () => {
            return new Promise((resolve, reject) => {
              const api = getApiInstance();
              api({ url: objectsUrl, method: 'GET' })
                .then((response) => resolve(response.data.data))
                .catch((err) => reject(err));
            });
          }
        }
      );
    },

    setExtraParameters: function (treeItem, sid, did) {
      const treeInfo = pgBrowser.tree.getTreeNodeHierarchy(
        pgBrowser.tree.findNodeByDomElement(pgBrowser.tree.selected())
      );
      return {
        database: treeInfo.database?._label,
        did: did,
        output_type: 'file',
        // Defaults: Heidi-style usually wants plain SQL
        format: 'plain',
      };
    },
  };

  return pgBrowser.SqlExport;
});

