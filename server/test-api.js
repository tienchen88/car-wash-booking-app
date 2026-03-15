const http = require('http');

const test = (path, method, data) => {
  return new Promise((resolve) => {
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: path,
      method: method,
      headers: {
        'Content-Type': 'application/json',
      }
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => resolve(JSON.parse(body)));
    });

    if (data) req.write(JSON.stringify(data));
    req.end();
  });
};

async function runTests() {
  console.log('--- 開始 API 邏輯驗證 ---');

  // 1. 測試登入
  const loginRes = await test('/api/login', 'POST', { phone: '0912345678', password: '123456' });
  console.log('登入測試結果:', loginRes.success ? '成功' : '失敗');

  // 2. 測試查詢時段
  const slotsRes = await test('/api/slots?date=2026-03-15', 'GET');
  console.log('時段查詢測試結果: 取得', slotsRes.length, '個時段');

  // 3. 測試預約 (預約第 1 個時段)
  const bookingRes = await test('/api/bookings', 'POST', {
    user_id: 1,
    slot_id: 1,
    booking_date: '2026-03-15'
  });
  console.log('預約功能測試結果:', bookingRes.success ? '預約成功' : '預約失敗: ' + bookingRes.error);

  console.log('--- 驗證結束 ---');
}

runTests();
