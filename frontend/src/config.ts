// 根據環境自動切換 API 網址
// 在開發環境下使用 localhost，在雲端環境下可以使用環境變數
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001';
