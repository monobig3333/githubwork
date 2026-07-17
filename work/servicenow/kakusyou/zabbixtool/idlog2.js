　// 30秒おきに8回 = 4分
for (var i = 0; i < 8; i++) {
    var gr = new GlideRecord('em_connector_instance');
    gr.get('ff8092a6c3784710fd241f977a013166');
    gs.info(new GlideDateTime().getDisplayValue() +
            ' | sig=' + gr.getValue('last_event_signature') +
            ' | run=' + gr.getValue('running') +
            ' | last_run=' + gr.getValue('last_run_time'));
    if (i < 7) gs.sleep(30000);
}