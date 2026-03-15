import React, { useState } from 'react';
import './App.css';
import { API_BASE_URL } from './config';

interface LoginViewProps {
  onLoginSuccess: (user: { id: number, name: string }) => void;
}

function LoginView({ onLoginSuccess }: LoginViewProps) {
  const [isRegister, setIsRegister] = useState(false);
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const endpoint = isRegister ? '/api/register' : '/api/login';
    const body = isRegister ? { phone, name, password } : { phone, password };

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const result = await response.json();

      if (response.ok && result.success) {
        // 登入成功，將用戶資訊傳回父組件
        onLoginSuccess(isRegister ? { id: result.user_id, name } : result.user);
      } else {
        setError(result.error || result.message || '操作失敗');
      }
    } catch (err) {
      setError('連線失敗，請確保後端伺服器已啟動');
    }
  };

  return (
    <div className="app-container" style={{ justifyContent: 'center' }}>
      <header style={{ border: 'none' }}>
        <div className="car-icon" style={{ fontSize: '4rem' }}>🏎️</div>
        <h1 style={{ fontSize: '2rem' }}>Turbo Wash</h1>
        <p style={{ color: '#888' }}>專業洗車，極速預約</p>
      </header>

      <div className="card">
        <h3>{isRegister ? '加入會員' : '歡迎回來'}</h3>
        <form onSubmit={handleSubmit}>
          {isRegister && (
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '0.8rem', color: '#ff6b00' }}>您的姓名</label>
              <input 
                type="text" 
                value={name} 
                onChange={(e) => setName(e.target.value)}
                placeholder="輸入姓名"
                style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#222', border: '1px solid #444', color: 'white' }}
                required
              />
            </div>
          )}
          
          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '0.8rem', color: '#ff6b00' }}>手機號碼</label>
            <input 
              type="tel" 
              value={phone} 
              onChange={(e) => setPhone(e.target.value)}
              placeholder="0912345678"
              style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#222', border: '1px solid #444', color: 'white' }}
              required
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '0.8rem', color: '#ff6b00' }}>密碼</label>
            <input 
              type="password" 
              value={password} 
              onChange={(e) => setPassword(e.target.value)}
              placeholder="輸入密碼"
              style={{ width: '100%', padding: '12px', borderRadius: '8px', background: '#222', border: '1px solid #444', color: 'white' }}
              required
            />
          </div>

          {error && <p style={{ color: '#ff4444', fontSize: '0.8rem', marginBottom: '15px' }}>{error}</p>}

          <button type="submit" className="btn-book" style={{ width: '100%', marginTop: '10px' }}>
            {isRegister ? '立即註冊' : '登入系統'}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.9rem', color: '#888' }}>
          {isRegister ? '已經有帳號了？' : '還不是會員？'}
          <span 
            onClick={() => setIsRegister(!isRegister)} 
            style={{ color: '#ff6b00', marginLeft: '5px', cursor: 'pointer', fontWeight: 'bold' }}
          >
            {isRegister ? '點此登入' : '立即加入'}
          </span>
        </p>
      </div>
    </div>
  );
}

export default LoginView;
