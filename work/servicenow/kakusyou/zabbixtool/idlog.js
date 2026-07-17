var gr = new GlideRecord('em_connector_instance');
gr.get('ff8092a6c3784710fd241f977a013166');
gs.info('[MONITOR] ' + new GlideDateTime().getDisplayValue() +
        ' | sig=' + gr.getValue('last_event_signature') +
        ' | last_run=' + gr.getValue('last_run_time') +
        ' | running=' + gr.getValue('running') +
        ' | status=' + gr.getValue('last_status'));