var CONNECTOR_SYS_ID = 'ff8092a6c3784710fd241f977a013166';
var NEW_SIGNATURE = '503300';  // ★ Zabbix最新の少し上に調整

var gr = new GlideRecord('em_connector_instance');
if (!gr.get(CONNECTOR_SYS_ID)) {
    gs.info('not found');
} else {
    gs.info('=== 修正前 ===');
    gs.info('  active               = ' + gr.getValue('active'));
    gs.info('  running              = ' + gr.getValue('running'));
    gs.info('  last_event_signature = ' + gr.getValue('last_event_signature'));
    gs.info('  last_run_time        = ' + gr.getValue('last_run_time'));

    // 無効化
    gr.setValue('active', '0');
    gr.update();

    // running リセット
    gr.setValue('running', '0');
    gr.update();

    // signature 再設定
    gr.setValue('last_event_signature', NEW_SIGNATURE);
    gr.update();

    // 再有効化
    gr.setValue('active', '1');
    gr.update();

    // 確認
    gr.get(CONNECTOR_SYS_ID);
    gs.info('=== 修正後 ===');
    gs.info('  active               = ' + gr.getValue('active'));
    gs.info('  running              = ' + gr.getValue('running'));
    gs.info('  last_event_signature = ' + gr.getValue('last_event_signature'));
    gs.info('  last_run_time        = ' + gr.getValue('last_run_time'));
    gs.info('→ 30秒〜1分待って、last_run_time が更新されることを確認');
}