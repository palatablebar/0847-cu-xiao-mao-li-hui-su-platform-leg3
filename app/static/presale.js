(function () {
  function $(id) { return document.getElementById(id); }
  function numberValue(id) {
    var value = $(id).value.trim();
    return value === '' ? undefined : Number(value);
  }
  function quotePayload() {
    return {
      sku: $('ps-sku').value.trim(),
      sell_price_cents: numberValue('ps-sell'),
      quote_low_cents: numberValue('ps-low'),
      quote_high_cents: numberValue('ps-high'),
      unit_margin_floor_cents: numberValue('ps-floor')
    };
  }
  async function request(url, options) {
    var response = await fetch(url, Object.assign(
      {headers: {'Content-Type': 'application/json'}},
      options || {}
    ));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      throw new Error(data.code || data.error || ('HTTP ' + response.status));
    }
    return data;
  }
  function show(data, message) {
    var eligible = Boolean(data.can_resell || data.eligible);
    var status = data.status || data.state || 'UNKNOWN';
    var credential = data.credential || null;
    var credentialState = credential ? (credential.status || credential.state) : '无';
    $('presale-status').textContent = message || status;
    $('ps-answer').innerHTML =
      '<strong data-eligible="' + eligible + '">' +
      (eligible ? '该商品可续卖' : '该商品不可续卖') +
      '</strong><span>状态：' + status + '</span>' +
      '<span>凭据：' + credentialState + '</span>' +
      '<span>凭据数：' + (data.credential_count == null ? '-' : data.credential_count) + '</span>' +
      '<span>原因：' + (data.reason || '-') + '</span>';
    $('ps-result').hidden = false;
    $('ps-result').textContent = JSON.stringify(data, null, 2);
  }
  function fail(error) {
    $('presale-status').textContent = '操作失败';
    $('ps-answer').textContent = error.message;
  }
  async function evaluate() {
    try { show(await request('/api/resale/quotes', {method: 'POST', body: JSON.stringify(quotePayload())}), '报价已处理'); }
    catch (error) { fail(error); }
  }
  async function rerun() {
    try {
      var sku = $('ps-sku').value.trim();
      show(await request('/api/resale/products/' + encodeURIComponent(sku) + '/rerun', {method: 'POST'}), '同一报价已重跑');
    } catch (error) { fail(error); }
  }
  async function query() {
    try {
      var sku = $('ps-sku').value.trim();
      show(await request('/api/resale/eligibility/' + encodeURIComponent(sku)), '查询完成');
    } catch (error) { fail(error); }
  }
  async function actual() {
    try {
      var payload = {sku: $('ps-sku').value.trim(), actual_cost_cents: numberValue('ps-actual')};
      show(await request('/api/resale/actual-prices', {method: 'POST', body: JSON.stringify(payload)}), '实价已处理');
    } catch (error) { fail(error); }
  }
  async function ship() {
    try {
      var payload = {
        sku: $('ps-sku').value.trim(),
        line_qty: numberValue('ps-qty'),
        sell_price_cents: numberValue('ps-sell'),
        unit_cost_cents: numberValue('ps-ship-cost')
      };
      var saved = await request('/api/resale/shipments', {method: 'POST', body: JSON.stringify(payload)});
      $('presale-status').textContent = '已出货毛利：' + saved.margin_cents + ' 分（后续重算不改写）';
      await query();
    } catch (error) { fail(error); }
  }
  document.addEventListener('DOMContentLoaded', function () {
    $('ps-evaluate').addEventListener('click', evaluate);
    $('ps-rerun').addEventListener('click', rerun);
    $('ps-query').addEventListener('click', query);
    $('ps-actual-submit').addEventListener('click', actual);
    $('ps-ship').addEventListener('click', ship);
  });
})();
