var CONNECTOR_SYS_ID = 'ff8092a6c3784710fd241f977a013166';

function upsertParam(name, value) {
    var gr = new GlideRecord('em_connector_instance_value');
    gr.addQuery('connector_instance', CONNECTOR_SYS_ID);
    gr.addQuery('name', name);
    gr.query();
    if (gr.next()) {
        var oldVal = gr.getValue('value');
        gr.setValue('value', value);
        gr.update();
        gs.info(name + ': "' + oldVal + '" → "' + value + '"');
    } else {
        var gr2 = new GlideRecord('em_connector_instance_value');
        gr2.initialize();
        gr2.setValue('connector_instance', CONNECTOR_SYS_ID);
        gr2.setValue('name', name);
        gr2.setValue('value', value);
        gr2.insert();
        gs.info(name + ': (新規) = "' + value + '"');
    }
}

// 最初に確認した値を全部書き戻す
upsertParam('api_endpoint_suffix', '/zabbix/api_jsonrpc.php');
upsertParam('days_from', '7');
upsertParam('debug', 'false');
upsertParam('enable_batch_processing', 'true');
upsertParam('logPayloadForDebug', 'true');
upsertParam('max_hosts_per_batch', '5000');
upsertParam('port', '443');
upsertParam('protocol', 'https');

gs.info('');
gs.info('===== 復旧完了 =====');