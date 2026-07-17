// ============================================================
// ServiceNow Background Script
// test-servicenow-monohyouka-XXXXX (末尾5桁) のイベント数を
// 11:18-11:35 の期間でカウント
// 対象テーブル: em_event (Event Management)
// ============================================================

(function countEvents() {

    // ---- パラメータ ----
    var nodePrefix     = 'test-servicenow-monohyouka-';   // 前方一致パターン
    var suffixRegex    = /^test-servicenow-monohyouka-.{5}$/;  // 末尾5桁判定 (任意の1文字×5)
    // 数字限定にしたい場合: /^test-servicenow-monohyouka-\d{5}$/
    // 英数字限定にしたい場合: /^test-servicenow-monohyouka-[A-Za-z0-9]{5}$/
    var targetDateJST  = '2026-06-03';                     // 対象日 (JST)
    var startTimeJST   = '11:18:00';
    var endTimeJST     = '11:35:00';

    // ---- JST → UTC 変換 ----
    var gdtStart = new GlideDateTime();
    gdtStart.setDisplayValue(targetDateJST + ' ' + startTimeJST);

    var gdtEnd = new GlideDateTime();
    gdtEnd.setDisplayValue(targetDateJST + ' ' + endTimeJST);

    gs.info('=== 集計期間 ===');
    gs.info('Start (JST): ' + gdtStart.getDisplayValue() + ' / (UTC): ' + gdtStart.getValue());
    gs.info('End   (JST): ' + gdtEnd.getDisplayValue()   + ' / (UTC): ' + gdtEnd.getValue());
    gs.info('Suffix Regex: ' + suffixRegex);

    // ---- 検索 (前方一致で取得 → JS側で正規表現フィルタ) ----
    var gr = new GlideRecord('em_event');
    gr.addQuery('node', 'STARTSWITH', nodePrefix);
    gr.addQuery('time_of_event', '>=', gdtStart);
    gr.addQuery('time_of_event', '<',  gdtEnd);   // 17:30ちょうどを含めたい場合は '<=' に変更
    gr.query();

    var total = 0;
    var rejected = 0;
    var countByNode = {};

    while (gr.next()) {
        var node = gr.getValue('node') + '';   // 文字列化
        if (!suffixRegex.test(node)) {
            rejected++;
            gs.info('Rejected node: [' + node + '] length=' + node.length);
            continue;
        }
        countByNode[node] = (countByNode[node] || 0) + 1;
        total++;
    }

    // ---- 結果出力 ----
    gs.info('=== ノード別件数 (5桁判定通過のみ) ===');
    var nodes = Object.keys(countByNode).sort();
    for (var i = 0; i < nodes.length; i++) {
        gs.info(nodes[i] + ' : ' + countByNode[nodes[i]] + ' 件');
    }

    gs.info('=== サマリ ===');
    gs.info('Total (5桁マッチ)  : ' + total + ' 件');
    gs.info('Rejected (桁数不一致): ' + rejected + ' 件');
    gs.info('ユニークノード数    : ' + nodes.length);

})();