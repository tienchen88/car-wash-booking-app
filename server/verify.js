const sqlite3 = require('sqlite3').verbose();
const db = new sqlite3.Database('./database.sqlite');

db.serialize(() => {
  // 嘗試插入王小明
  db.run("INSERT OR IGNORE INTO users (phone, name, password) VALUES ('0912345678', '王小明', '123456')", (err) => {
    if (err) console.error('插入失敗:', err);
  });

  // 讀取出來看看
  db.all('SELECT * FROM users', [], (err, rows) => {
    if (err) {
      console.error('查詢失敗:', err);
    } else {
      console.log('--- 資料庫驗證結果 ---');
      console.log('成功讀取使用者資料:', rows);
    }
    db.close();
  });
});
