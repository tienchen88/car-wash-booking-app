import React, { useState, useEffect } from 'react';
import './App.css';
import { API_BASE_URL } from './config';

interface Booking {
  id: number;
  booking_date: string;
  start_time: string;
  end_time: string;
  status: string;
}

interface MyBookingsProps {
  userId: number;
  onBack: () => void;
}

function MyBookingsView({ userId, onBack }: MyBookingsProps) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchMyBookings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/my-bookings/${userId}`);
      const data = await response.json();
      setBookings(data);
    } catch (error) {
      console.error('抓取紀錄失敗:', error);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchMyBookings();
  }, [userId]);

  const handleCancel = async (bookingId: number) => {
    if (!window.confirm('確定要取消這個預約嗎？')) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/bookings/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ booking_id: bookingId, user_id: userId })
      });
      const result = await response.json();
      if (result.success) {
        alert('預約已取消');
        fetchMyBookings(); // 重新整理清單
      }
    } catch (error) {
      alert('取消失敗，請稍後再試');
    }
  };

  return (
    <div className="app-container">
      <header>
        <div className="car-icon">📅</div>
        <h1>我的預約紀錄</h1>
      </header>

      <div style={{ flex: 1 }}>
        {loading ? (
          <p style={{ textAlign: 'center' }}>載入中...</p>
        ) : bookings.length === 0 ? (
          <div className="card" style={{ textAlign: 'center' }}>
            <p style={{ color: '#888' }}>目前沒有任何預約紀錄</p>
            <button className="btn-book" onClick={onBack} style={{ fontSize: '0.9rem', padding: '10px 20px' }}>
              立即去預約
            </button>
          </div>
        ) : (
          bookings.map(b => (
            <div key={b.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ color: '#ff6b00', fontWeight: 'bold', fontSize: '1.1rem' }}>{b.booking_date}</div>
                <div style={{ color: '#fff', marginTop: '5px' }}>{b.start_time} - {b.end_time}</div>
              </div>
              <button 
                onClick={() => handleCancel(b.id)}
                style={{
                  background: 'none', 
                  border: '1px solid #ff4444', 
                  color: '#ff4444', 
                  padding: '5px 12px', 
                  borderRadius: '20px', 
                  fontSize: '0.8rem',
                  cursor: 'pointer'
                }}
              >
                取消
              </button>
            </div>
          ))
        )}
      </div>

      <button className="btn-book" style={{ background: '#444' }} onClick={onBack}>
        返回主頁
      </button>
    </div>
  );
}

export default MyBookingsView;
