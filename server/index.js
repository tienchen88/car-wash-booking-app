require('dotenv').config();
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const path = require('path');
const bcrypt = require('bcrypt');

const SALT_ROUNDS = 10;
const ADMIN_PHONE = process.env.ADMIN_PHONE || '';

const app = express();
const port = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

const dbPath = path.join(__dirname, 'database.sqlite');
const db = new sqlite3.Database(dbPath);

db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password TEXT NOT NULL
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS time_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    max_capacity INTEGER DEFAULT 1
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    booking_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    group_id TEXT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (slot_id) REFERENCES time_slots (id)
  )`);

  // Migration: 為舊資料庫加上 group_id 欄位（若已存在則忽略錯誤）
  db.run(`ALTER TABLE bookings ADD COLUMN group_id TEXT DEFAULT NULL`, () => {});

  // 效能索引
  db.run(`CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date)`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(slot_id)`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)`);

  db.get("SELECT COUNT(*) as count FROM time_slots", (err, row) => {
    if (row && row.count === 0) {
      const defaultSlots = [
        ['09:00', '10:00'], ['10:00', '11:00'], ['11:00', '12:00'],
        ['13:00', '14:00'], ['14:00', '15:00'], ['15:00', '16:00'],
        ['16:00', '17:00'], ['17:00', '18:00']
      ];
      const stmt = db.prepare("INSERT INTO time_slots (start_time, end_time) VALUES (?, ?)");
      defaultSlots.forEach(slot => stmt.run(slot[0], slot[1]));
      stmt.finalize();
      console.log('資料庫初始化：已插入預設時段');
    }
  });
});

// --- 管理員驗證 Middleware ---
function requireAdmin(req, res, next) {
  const userId = req.query.user_id;
  if (!userId || !ADMIN_PHONE) return res.status(403).json({ error: '權限不足' });
  db.get("SELECT phone FROM users WHERE id = ?", [parseInt(userId, 10)], (err, user) => {
    if (err || !user || user.phone !== ADMIN_PHONE) return res.status(403).json({ error: '權限不足' });
    next();
  });
}

// --- API 路由 ---

// 健康檢查
app.get('/api/health', (req, res) => {
  res.json({ status: 'OK', message: '洗車預約後端已啟動' });
});

// 使用者註冊
app.post('/api/register', async (req, res) => {
  const { phone, name, password } = req.body;
  if (!phone || !name || !password) return res.status(400).json({ error: '請填寫完整資訊' });
  if (!/^09\d{8}$/.test(phone)) return res.status(400).json({ error: '請輸入有效的手機號碼（格式：09xxxxxxxx）' });
  if (password.length < 6) return res.status(400).json({ error: '密碼至少需要 6 個字元' });

  try {
    const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);
    db.run(`INSERT INTO users (phone, name, password) VALUES (?, ?, ?)`, [phone, name, hashedPassword], function(err) {
      if (err) {
        if (err.message.includes('UNIQUE')) return res.status(400).json({ error: '此電話號碼已註冊過' });
        return res.status(500).json({ error: '註冊失敗' });
      }
      res.json({ success: true, user_id: this.lastID });
    });
  } catch (err) {
    res.status(500).json({ error: '伺服器錯誤' });
  }
});

// 使用者登入
app.post('/api/login', (req, res) => {
  const { phone, password } = req.body;
  if (!phone || !password) return res.status(400).json({ error: '請填寫完整資訊' });

  db.get("SELECT id, name, phone, password FROM users WHERE phone = ?", [phone], async (err, user) => {
    if (err) return res.status(500).json({ error: '資料庫錯誤' });
    if (!user) return res.status(401).json({ success: false, message: '電話或密碼錯誤' });

    try {
      const match = await bcrypt.compare(password, user.password);
      if (!match) return res.status(401).json({ success: false, message: '電話或密碼錯誤' });
      res.json({
        success: true,
        user: {
          id: user.id,
          name: user.name,
          is_admin: !!(ADMIN_PHONE && user.phone === ADMIN_PHONE)
        }
      });
    } catch (err) {
      res.status(500).json({ error: '伺服器錯誤' });
    }
  });
});

// 取得特定日期的時段狀態
app.get('/api/slots', (req, res) => {
  const { date } = req.query;
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return res.status(400).json({ error: '請提供有效日期（格式：YYYY-MM-DD）' });

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

// 提交預約（支援多時長，含 transaction 防止 race condition）
app.post('/api/bookings', (req, res) => {
  const { user_id, slot_id, booking_date, service_type } = req.body;

  const slotIdNum = parseInt(slot_id, 10);
  const userIdNum = parseInt(user_id, 10);
  if (!userIdNum || isNaN(slotIdNum) || !booking_date || !/^\d{4}-\d{2}-\d{2}$/.test(booking_date)) {
    return res.status(400).json({ error: '資料不完整或格式錯誤' });
  }

  const isTwoHours = service_type === 'wash_wax';
  const slotsToCheck = isTwoHours ? [slotIdNum, slotIdNum + 1] : [slotIdNum];
  const placeholders = slotsToCheck.map(() => '?').join(',');

  const checkQuery = `
    SELECT ts.id, ts.max_capacity,
    (SELECT COUNT(*) FROM bookings b WHERE b.slot_id = ts.id AND b.booking_date = ? AND b.status != 'cancelled') as current_count
    FROM time_slots ts WHERE ts.id IN (${placeholders})
  `;

  // BEGIN IMMEDIATE 鎖定資料庫，防止同時預約的 race condition
  db.run('BEGIN IMMEDIATE', (beginErr) => {
    if (beginErr) return res.status(500).json({ error: '預約失敗，請再試一次' });

    db.all(checkQuery, [booking_date, ...slotsToCheck], (err, rows) => {
      if (err) {
        db.run('ROLLBACK');
        return res.status(500).json({ error: '檢查失敗' });
      }
      if (rows.length !== slotsToCheck.length) {
        db.run('ROLLBACK');
        return res.status(400).json({ error: '所選時段跨越營業時間，請選擇較早的時段' });
      }
      const isAvailable = rows.every(row => row.current_count < row.max_capacity);
      if (!isAvailable) {
        db.run('ROLLBACK');
        return res.status(400).json({ error: '該時段或後續時段已約滿' });
      }

      const group_id = isTwoHours ? Date.now().toString() : null;
      const insertQuery = `INSERT INTO bookings (user_id, slot_id, booking_date, status, group_id) VALUES (?, ?, ?, 'pending', ?)`;

      let completed = 0;
      let hasError = false;

      slotsToCheck.forEach(id => {
        db.run(insertQuery, [userIdNum, id, booking_date, group_id], function(err) {
          if (err) hasError = true;
          completed++;
          if (completed === slotsToCheck.length) {
            if (hasError) {
              db.run('ROLLBACK');
              return res.status(500).json({ error: '預約失敗，請再試一次' });
            }
            db.run('COMMIT');
            res.json({ success: true });
          }
        });
      });
    });
  });
});

// 查看使用者的預約紀錄
app.get('/api/my-bookings/:user_id', (req, res) => {
  const userId = parseInt(req.params.user_id, 10);
  if (isNaN(userId)) return res.status(400).json({ error: '無效的使用者 ID' });

  const query = `
    SELECT b.id, b.booking_date, b.status, b.group_id, ts.start_time, ts.end_time
    FROM bookings b
    JOIN time_slots ts ON b.slot_id = ts.id
    WHERE b.user_id = ? AND b.status != 'cancelled'
    ORDER BY b.booking_date DESC, ts.start_time ASC
  `;
  db.all(query, [userId], (err, rows) => {
    if (err) return res.status(500).json({ error: '查詢失敗' });
    res.json(rows);
  });
});

// 取消預約（2小時訂單會一起取消）
app.post('/api/bookings/cancel', (req, res) => {
  const { booking_id, user_id } = req.body;
  const bookingIdNum = parseInt(booking_id, 10);
  const userIdNum = parseInt(user_id, 10);
  if (isNaN(bookingIdNum) || isNaN(userIdNum)) return res.status(400).json({ error: '資料不完整' });

  db.get(`SELECT group_id FROM bookings WHERE id = ? AND user_id = ?`, [bookingIdNum, userIdNum], (err, row) => {
    if (err) return res.status(500).json({ error: '取消失敗' });
    if (!row) return res.status(404).json({ error: '找不到預約' });

    if (row.group_id) {
      // 2小時訂單：一起取消同群組的所有時段
      db.run(`UPDATE bookings SET status = 'cancelled' WHERE group_id = ? AND user_id = ?`, [row.group_id, userIdNum], function(err) {
        if (err) return res.status(500).json({ error: '取消失敗' });
        res.json({ success: true });
      });
    } else {
      db.run(`UPDATE bookings SET status = 'cancelled' WHERE id = ? AND user_id = ?`, [bookingIdNum, userIdNum], function(err) {
        if (err) return res.status(500).json({ error: '取消失敗' });
        res.json({ success: true });
      });
    }
  });
});

// 管理員：查看全場預約（需驗證）
app.get('/api/admin/all-bookings', requireAdmin, (req, res) => {
  const { date } = req.query;
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return res.status(400).json({ error: '請提供有效日期' });

  const query = `
    SELECT b.id, b.booking_date, b.status, b.group_id, u.name as user_name, u.phone as user_phone, ts.start_time, ts.end_time
    FROM bookings b
    JOIN users u ON b.user_id = u.id
    JOIN time_slots ts ON b.slot_id = ts.id
    WHERE b.booking_date = ? AND b.status != 'cancelled'
    ORDER BY ts.start_time ASC
  `;
  db.all(query, [date], (err, rows) => {
    if (err) return res.status(500).json({ error: '查詢失敗' });
    res.json(rows);
  });
});

app.listen(port, () => {
  console.log(`後端伺服器已啟動: http://localhost:${port}`);
});
