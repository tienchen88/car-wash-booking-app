const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const dbPath = path.join(__dirname, 'database.sqlite');
const db = new sqlite3.Database(dbPath);

db.serialize(() => {
  console.log('正在初始化資料庫...');

  // 1. 建立使用者資料表 (Users)
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password TEXT NOT NULL
  )`);

  // 2. 建立時段資料表 (TimeSlots)
  db.run(`CREATE TABLE IF NOT EXISTS time_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    max_capacity INTEGER DEFAULT 1
  )`);

  // 3. 建立預約紀錄資料表 (Bookings)
  db.run(`CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    booking_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (slot_id) REFERENCES time_slots (id)
  )`);

  console.log('資料表建立完成。');

  // 4. 插入一些預設的預約時段 (如果你想修改營業時段，可以改這裡)
  const defaultSlots = [
    ['09:00', '10:00'],
    ['10:00', '11:00'],
    ['11:00', '12:00'],
    ['13:00', '14:00'],
    ['14:00', '15:00'],
    ['15:00', '16:00'],
    ['16:00', '17:00'],
    ['17:00', '18:00']
  ];

  db.get("SELECT COUNT(*) as count FROM time_slots", (err, row) => {
    if (row.count === 0) {
      const stmt = db.prepare("INSERT INTO time_slots (start_time, end_time) VALUES (?, ?)");
      defaultSlots.forEach(slot => {
        stmt.run(slot[0], slot[1]);
      });
      stmt.finalize();
      console.log('已成功插入預設時段。');
    } else {
      console.log('時段已存在，跳過插入。');
    }
    // 確保所有動作完成後才關閉
    db.close();
  });
});
