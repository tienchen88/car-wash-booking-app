import React, { useState, useEffect } from 'react';
import './App.css';
import { API_BASE_URL } from './config';
import AdminView from './AdminView';
import LoginView from './LoginView';
import MyBookingsView from './MyBookingsView';

interface Slot {
  id: number;
  start_time: string;
  end_time: string;
  max_capacity: number;
  booked_count: number;
}

interface User {
  id: number;
  name: string;
}

type ServiceType = 'wash' | 'wash_wax';

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<'home' | 'admin' | 'my-bookings'>('home');
  const [selectedService, setSelectedService] = useState<ServiceType>('wash');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  // 產生未來 7 天的日期
  const getNext7Days = () => {
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      days.push(d.toISOString().split('T')[0]);
    }
    return days;
  };

  // 向後端抓取時段
  const fetchSlots = async (date: string) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/slots?date=${date}`);
      const data = await response.json();
      setSlots(data);
    } catch (error) {
      console.error('抓取時段失敗:', error);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (user && view === 'home') {
      fetchSlots(selectedDate);
      setSelectedSlot(null);
    }
  }, [selectedDate, user, view, selectedService]);

  // 送出預約
  const handleBooking = async () => {
    if (!selectedSlot || !user) return;
    const bookingData = {
      user_id: user.id,
      slot_id: selectedSlot,
      booking_date: selectedDate,
      service_type: selectedService
    };

    try {
      const response = await fetch(`${API_BASE_URL}/api/bookings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bookingData)
      });
      const result = await response.json();
      if (result.success) {
        alert(`🚗 預約成功！\n系統已為您保留所需的時長。`);
        fetchSlots(selectedDate);
        setSelectedSlot(null);
      } else {
        alert('預約失敗: ' + result.error);
      }
    } catch (error) {
      alert('連線失敗，請稍後再試');
    }
  };

  // 檢查時段是否可選 (如果是 2 小時，需檢查下一個時段)
  const isSlotSelectable = (index: number) => {
    const slot = slots[index];
    if (slot.booked_count >= slot.max_capacity) return false;
    
    if (selectedService === 'wash_wax') {
      const nextSlot = slots[index + 1];
      if (!nextSlot || nextSlot.booked_count >= nextSlot.max_capacity) return false;
    }
    return true;
  };

  if (!user) return <LoginView onLoginSuccess={(u) => setUser(u)} />;
  if (view === 'admin') return <AdminView onBack={() => setView('home')} />;
  if (view === 'my-bookings') return <MyBookingsView userId={user.id} onBack={() => setView('home')} />;

  return (
    <div className="app-container">
      <header>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <span style={{fontSize: '0.8rem', color: '#ff6b00'}}>你好, {user.name}</span>
          <div style={{display: 'flex', gap: '8px'}}>
            <button onClick={() => setView('my-bookings')} className="nav-btn">我的預約</button>
            <button onClick={() => setView('admin')} className="nav-btn">切換管理</button>
            <button onClick={() => setUser(null)} className="nav-btn">登出</button>
          </div>
        </div>
        <div className="car-icon">🏎️</div>
        <h1>Turbo Wash 預約系統</h1>
      </header>

      {/* 服務選擇區 */}
      <section className="card">
        <h3>選擇服務項目</h3>
        <div style={{display: 'flex', gap: '10px', marginTop: '10px'}}>
          <div 
            className={`service-btn ${selectedService === 'wash' ? 'active' : ''}`}
            onClick={() => setSelectedService('wash')}
          >
            <div>普通洗車</div>
            <div style={{fontSize: '0.7rem', opacity: 0.7}}>約 1 小時</div>
          </div>
          <div 
            className={`service-btn ${selectedService === 'wash_wax' ? 'active' : ''}`}
            onClick={() => setSelectedService('wash_wax')}
          >
            <div>洗車 + 打蠟</div>
            <div style={{fontSize: '0.7rem', opacity: 0.7}}>約 2 小時</div>
          </div>
        </div>
      </section>

      <section className="card">
        <h3>選擇日期</h3>
        <div className="date-selector">
          {getNext7Days().map(date => (
            <div 
              key={date} 
              className={`date-item ${selectedDate === date ? 'active' : ''}`}
              onClick={() => setSelectedDate(date)}
            >
              <div>{date.split('-')[2]}</div>
              <div style={{fontSize: '0.7rem'}}>{date.split('-')[1]}月</div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>選擇起始時段</h3>
        {loading ? (
          <p>掃描可用時段中...</p>
        ) : (
          <div className="slots-grid">
            {slots.map((slot, index) => {
              const selectable = isSlotSelectable(index);
              const isSelected = selectedSlot === slot.id;
              // 如果選了 2 小時，下一個時段也要亮起來
              const isPartofSelected = selectedService === 'wash_wax' && selectedSlot && slots[index-1]?.id === selectedSlot;

              return (
                <div 
                  key={slot.id} 
                  className={`slot-card ${!selectable ? 'booked' : ''} ${isSelected || isPartofSelected ? 'selected' : ''}`}
                  onClick={() => selectable && setSelectedSlot(slot.id)}
                >
                  <div className="slot-time">{slot.start_time}</div>
                  <div className="slot-status">{!selectable ? '不可預約' : `剩餘 ${slot.max_capacity - slot.booked_count} 位`}</div>
                </div>
              );
            })}
          </div>
        )}
        
        <div style={{
          marginTop: '20px', 
          textAlign: 'center', 
          fontSize: '0.85rem', 
          color: '#888',
          borderTop: '1px solid #333',
          paddingTop: '15px'
        }}>
          💡 若無需要的時段或有特殊需求？<br/>
          請撥打預約專線：
          <a href="tel:0912345678" style={{
            color: '#ff6b00', 
            textDecoration: 'none', 
            fontWeight: 'bold',
            marginLeft: '5px'
          }}>
            0912-345-678
          </a>
        </div>
      </section>

      <button className="btn-book" disabled={!selectedSlot} onClick={handleBooking}>
        立即預約 {selectedService === 'wash' ? '(1小時)' : '(2小時)'}
      </button>
    </div>
  );
}

export default App;
