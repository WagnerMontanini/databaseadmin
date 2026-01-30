/////////////////////////////////////////////////////////////
//
// pgAdmin 4 - PostgreSQL Tools
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import gettext from 'sources/gettext';
import BackupSchema, {
  getSectionSchema,
  getTypeObjSchema,
  getSaveOptSchema,
  getDisabledOptionSchema,
  getMiscellaneousSchema,
  getExcludePatternsSchema,
} from '../../../backup/static/js/backup.ui';
import getApiInstance from 'sources/api_instance';
import url_for from 'sources/url_for';
import _ from 'lodash';

/**
 * SQL Export schema (Heidi-style): reuse BackupSchema options and add
 * destination selection (File vs Target Server/Database).
 *
 * Notes:
 * - For output to server/database we force format=plain (SQL).
 * - We keep the objects tree from BackupSchema as-is.
 */
export default class SqlExportSchema extends BackupSchema {
  constructor(fieldOptions = {}, treeNodeInfo = [], pgBrowser = null, objects = {}) {
    super(
      () => getSectionSchema(),
      () => getTypeObjSchema(),
      () => getSaveOptSchema({ nodeInfo: treeNodeInfo }),
      () => getDisabledOptionSchema({ nodeInfo: treeNodeInfo }),
      () => getMiscellaneousSchema({ nodeInfo: treeNodeInfo }),
      () => getExcludePatternsSchema(),
      fieldOptions,
      treeNodeInfo,
      pgBrowser,
      'backup_objects',
      objects,
    );

    // Precisamos regenerar campos dinamicamente (depende do target.sid)
    this._dynamicFields = true;

    this._targetServers = [];
    this._targetDatabases = [];
  }

  _getTargetSid(state) {
    // Dependendo do SchemaView, campos com "." podem chegar como flat key.
    return state?.target?.sid ?? state?.['target.sid'] ?? null;
  }

  _isTargetServerConnected(sid) {
    return _.find(this._targetServers, (s) => `${s.value}` === `${sid}`)?.connected;
  }

  _loadTargetServers() {
    if (this._targetServers?.length) {
      return Promise.resolve(this._targetServers);
    }

    const api = getApiInstance();
    return api({
      url: url_for('sqleditor.get_new_connection_servers'),
      method: 'GET',
    }).then((resp) => {
      const serverGroupData = resp.data?.data?.result?.server_list || {};
      const options = [];

      Object.keys(serverGroupData).forEach((grp) => {
        serverGroupData[grp].forEach((s) => {
          options.push({
            ...s,
            label: `${s.label} (${grp})`,
          });
        });
      });

      this._targetServers = options;
      return options;
    });
  }

  _loadTargetDatabases(targetSid) {
    if (!targetSid) return Promise.resolve([]);
    if (!this._isTargetServerConnected(targetSid)) return Promise.resolve([]);

    const api = getApiInstance();
    return api({
      url: url_for('sqleditor.get_new_connection_database', { sid: targetSid, sgid: 0 }),
      method: 'GET',
    }).then((resp) => {
      const dbs = resp.data?.data?.result?.data || [];
      this._targetDatabases = dbs;
      return dbs;
    }).catch(() => {
      // Se falhar (ex.: não conectado), mantemos vazio e deixamos usuário digitar.
      return [];
    });
  }

  get baseFields() {
    const base = super.baseFields;

    const destinationFields = [
      {
        id: 'output_type',
        label: gettext('Output'),
        type: 'select',
        controlProps: { allowClear: false, noEmpty: true, width: '100%' },
        options: [
          { label: gettext('File'), value: 'file' },
          { label: gettext('Server/Database'), value: 'server' },
        ],
        deps: ['output_type'],
        depChange: (state) => {
          // When exporting to server/database, force PLAIN SQL output
          if (state.output_type === 'server') {
            return { format: 'plain' };
          }
          return {};
        },
      },
      {
        id: 'target.sid',
        label: gettext('Target server'),
        deps: ['output_type'],
        visible: (state) => state.output_type === 'server',
        controlProps: { allowClear: false, noEmpty: true, width: '100%' },
        type: () => ({
          type: 'select',
          options: () => this._loadTargetServers(),
        }),
      },
      {
        id: 'target.database',
        label: gettext('Target database'),
        deps: ['output_type', 'target.sid'],
        visible: (state) => state.output_type === 'server',
        type: (state) => ({
          type: 'select',
          controlProps: { allowClear: true, creatable: true, width: '100%' },
          options: () => this._loadTargetDatabases(this._getTargetSid(state)),
          optionsReloadBasis: `${this._getTargetSid(state)} ${this._isTargetServerConnected(this._getTargetSid(state))}`,
        }),
        helpMessage: gettext('Database to apply the SQL into. If you enable "Include CREATE DATABASE", this can be left empty.'),
      },
      {
        id: 'target.initial_database',
        label: gettext('Initial database'),
        type: 'text',
        visible: (state) => state.output_type === 'server',
        helpMessage: gettext('Database used for the initial psql connection. Useful when using CREATE DATABASE. Defaults to postgres.'),
      },
    ];

    // Inject destination fields at the beginning of General group.
    // Also make the Filename field required only when output_type=file.
    const updated = [];
    for (const f of base) {
      if (f.id === 'file') {
        updated.push({
          ...f,
          deps: [...(f.deps || []), 'output_type'],
          visible: (state) => state.output_type !== 'server',
        });
        continue;
      }
      if (f.id === 'format') {
        updated.push({
          ...f,
          deps: [...(f.deps || []), 'output_type'],
          disabled: (state) => state.output_type === 'server',
        });
        continue;
      }
      updated.push(f);
    }

    return [...destinationFields, ...updated];
  }

  validate(state, setError) {
    // File is required only when output_type=file
    if (state.output_type !== 'server' && !state.file) {
      setError('file', gettext('Please provide a filename.'));
      return true;
    }
    setError('file', null);

    if (state.output_type === 'server') {
      const targetSid = this._getTargetSid(state);
      if (!targetSid) {
        setError('target.sid', gettext('Please select a target server.'));
        return true;
      }
      setError('target.sid', null);
      // target.database can be empty when CREATE DATABASE enabled
    }
    return super.validate(state, setError);
  }
}

