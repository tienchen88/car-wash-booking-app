require('dotenv').config(); // 載入環境變數
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const path = require('path');

const app = express();
const port = process.env.PORT || 3001; // 雲端會自動分配 Port，若無則預設 3001

// 允許跨來源請求 (讓前端 Vercel 能連過來)
app.use(cors());
app.use(express.json());

// 連接資料庫並初始化資料表
const dbPath = path.join(__dirname, 'database.sqlite');
const db = new sqlite3.Database(dbPath);

db.serialize(() => {
  // 建立使用者表
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password TEXT NOT NULL
  )`);

  // 建立時段表
  db.run(`CREATE TABLE IF NOT EXISTS time_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    max_capacity INTEGER DEFAULT 1
  )`);

  // 建立預約表
  db.run(`CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    booking_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (slot_id) REFERENCES time_slots (id)
  )`);

  // 預先填入時段 (若為空)
  db.get("SELECT COUNT(*) as count FROM time_slots", (err, row) => {
    if (row && row.count === 0) {
      const defaultSlots = [['09:00', '10:00'], ['10:00', '11:00'], ['11:00', '12:00'], ['13:00', '14:00'], ['14:00', '15:00'], ['15:00', '16:00'], ['16:00', '17:00'], ['17:00', '18:00']];
      const stmt = db.prepare("INSERT INTO time_slots (start_time, end_time) VALUES (?, ?)");
      defaultSlots.forEach(slot => stmt.run(slot[0], slot[1]));
      stmt.finalize();
      console.log('雲端資料庫初始化：已插入預設時段');
    }
  });
});

// --- API 路由設計 ---

// 1. 測試 API 是否正常運作
app.get('/api/health', (req, res) => {
  res.json({ status: 'OK', message: '洗車預約後端已啟動' });
});

// 1.5 使用者註冊
app.post('/api/register', (req, res) => {
  const { phone, name, password } = req.body;
  if (!phone || !name || !password) return res.status(400).json({ error: '請填寫完整資訊' });

  const query = `INSERT INTO users (phone, name, password) VALUES (?, ?, ?)`;
  db.run(query, [phone, name, password], function(err) {
    if (err) {
      if (err.message.includes('UNIQUE')) return res.status(400).json({ error: '此電話號碼已註冊過' });
      return res.status(500).json({ error: '註冊失敗' });
    }
    res.json({ success: true, user_id: this.lastID });
  });
});

// 2. 使用者登入 (簡化版：僅檢查手機與密碼)
app.post('/api/login', (req, res) => {
  const { phone, password } = req.body;
  db.get("SELECT id, name, phone FROM users WHERE phone = ? AND password = ?", [phone, password], (err, user) => {
    if (err) return res.status(500).json({ error: '資料庫錯誤' });
    if (user) {
      res.json({ success: true, user });
    } else {
      res.status(401).json({ success: false, message: '電話或密碼錯誤' });
    }
  });
});

// 3. 取得特定日期的時段狀態
app.get('/api/slots', (req, res) => {
  const { date } = req.query; // 格式: YYYY-MM-DD
  if (!date) return res.status(400).json({ error: '請提供日期' });

  // 查詢所有時段，並計算該日期每個時段已預約的人數
  const query = `
    SELECT ts.*, 
    (SELECT COUNT(*) FROM bookings b WHERE b.slot_id = ts.id AND b.booking_date = ? AND b.status != 'cancelled') as booked_count
    FROM time_slots ts
  `;

  db.all(query, [date], (err, rows) => {
    if (err) return res.status(500).json({ error: '查詢失敗' });
    res.json(rows);
  });
});

// 4. 提交預約 (核心邏輯 - 支援多時長)
app.post('/api/bookings', (req, res) => {
  const { user_id, slot_id, booking_date, service_type } = req.body;
  const isTwoHours = service_type === 'wash_wax'; // 是否為 2 小時服務

  // 步驟 A: 檢查時段可用性
  // 如果是 2 小時，需要檢查 slot_id 和 slot_id + 1
  const slotsToCheck = isTwoHours ? [slot_id, slot_id + 1] : [slot_id];
  
  const checkQuery = `
    SELECT ts.id, ts.max_capacity, 
    (SELECT COUNT(*) FROM bookings b WHERE b.slot_id = ts.id AND b.booking_date = ? AND b.status != 'cancelled') as current_count
    FROM time_slots ts WHERE ts.id IN (${slotsToCheck.join(',')})
  `;

  db.all(checkQuery, [booking_date], (err, rows) => {
    if (err) return res.status(500).json({ error: '檢查失敗' });
    
    // 檢查是否所有需要的時段都存在且未滿
    if (rows.length !== slotsToCheck.length) {
      return res.status(400).json({ error: '所選時段跨越營業時間，請選擇較早的時段' });
    }

    const isAvailable = rows.every(row => row.current_count < row.max_capacity);
    if (!isAvailable) {
      return res.status(400).json({ error: '該時段或後續時段已約滿' });
    }

    // 步驟 B: 執行預約 (若為 2 小時則插入兩筆紀錄)
    const group_id = Date.now(); // 用時間戳當作群組 ID，方便一起取消
    const insertQuery = `INSERT INTO bookings (user_id, slot_id, booking_date, status) VALUES (?, ?, ?, ?)`;
    
    let completed = 0;
    slotsToCheck.forEach(id => {
      db.run(insertQuery, [user_id, id, booking_date, group_id.toString()], function(err) {
        completed++;
        if (completed === slotsToCheck.length) {
          res.json({ success: true });
        }
      });
    });
  });
});

// 5. 查看使用者的預約紀錄
app.get('/api/my-bookings/:user_id', (req, res) => {
  const query = `
    SELECT b.*, ts.start_time, ts.end_time 
    FROM bookings b
    JOIN time_slots ts ON b.slot_id = ts.id
    WHERE b.user_id = ? AND b.status != 'cancelled'
    ORDER BY b.booking_date DESC, ts.start_time ASC
  `;
  db.all(query, [req.params.user_id], (err, rows) => {
    if (err) return res.status(500).json({ error: '查詢失敗' });
    res.json(rows);
  });
});

// 5.5 取消預約
app.post('/api/bookings/cancel', (req, res) => {
  const { booking_id, user_id } = req.body;
  const query = `UPDATE bookings SET status = 'cancelled' WHERE id = ? AND user_id = ?`;
  db.run(query, [booking_id, user_id], function(err) {
    if (err) return res.status(500).json({ error: '取消失敗' });
    res.json({ success: true });
  });
});

// 6. (管理員) 查看全場預約
app.get('/api/admin/all-bookings', (req, res) => {
  const { date } = req.query;
  const query = `
    SELECT b.id, b.booking_date, b.status, u.name as user_name, u.phone as user_phone, ts.start_time, ts.end_time
    FROM bookings b
    JOIN users u ON b.user_id = u.id
    JOIN time_slots ts ON b.slot_id = ts.id
    WHERE b.booking_date = ?
    ORDER BY ts.start_time ASC
  `;
  db.all(query, [date], (err, rows) => {
    if (err) return res.status(500).json({ error: '查詢失敗' });
    res.json(rows);
  });
});

// 啟動伺服器
app.listen(port, () => {
  console.log(`後端伺服器已啟動: http://localhost:${port}`);
});
