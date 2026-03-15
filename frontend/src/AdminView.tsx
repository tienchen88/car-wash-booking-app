import React, { useState, useEffect } from 'react';
import './App.css';
import { API_BASE_URL } from './config';

interface BookingRecord {
  id: number;
  user_name: string;
  user_phone: string;
  start_time: string;
  end_time: string;
  status: string;
}

interface AdminViewProps {
  onBack: () => void;
}

function AdminView({ onBack }: AdminViewProps) {
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [bookings, setBookings] = useState<BookingRecord[]>([]);

  const fetchAllBookings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/all-bookings?date=${date}`);
      const data = await response.json();
      setBookings(data);
    } catch (error) {
      console.error('抓取失敗:', error);
    }
  };

  useEffect(() => {
    fetchAllBookings();
  }, [date]);

  return (
    <div className="app-container">
      <header>
        <div className="car-icon">🛠️</div>
        <h1>管理員控制台</h1>
        <p style={{color: '#ff6b00', fontSize: '0.8rem'}}>今日營運概況</p>
      </header>

      {/* ... (中間部分不變) */}

      <div className="card">
        <h3>當日預約清單 ({bookings.length} 台)</h3>
        {bookings.length === 0 ? (
          <p style={{textAlign: 'center', color: '#888'}}>本日尚無預約</p>
        ) : (
          <div style={{overflowX: 'auto'}}>
            <table style={{width: '100%', borderCollapse: 'collapse', marginTop: '10px'}}>
              <thead>
                <tr style={{borderBottom: '1px solid #444', color: '#ff6b00'}}>
                  <th style={{textAlign: 'left', padding: '8px'}}>時段</th>
                  <th style={{textAlign: 'left', padding: '8px'}}>客戶</th>
                  <th style={{textAlign: 'left', padding: '8px'}}>電話</th>
                </tr>
              </thead>
              <tbody>
                {bookings.map(b => (
                  <tr key={b.id} style={{borderBottom: '1px solid #333'}}>
                    <td style={{padding: '12px 8px'}}>{b.start_time}</td>
                    <td style={{padding: '12px 8px'}}>{b.user_name}</td>
                    <td style={{padding: '12px 8px', color: '#888'}}>{b.user_phone}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <button 
        className="btn-book" 
        style={{background: '#444', marginTop: '20px'}}
        onClick={onBack}
      >
        返回主頁
      </button>
    </div>
  );
}

export default AdminView;
