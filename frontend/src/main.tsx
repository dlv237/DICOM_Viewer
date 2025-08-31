import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import StudyViewer from './study/StudyViewer'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path=":id" element={<StudyViewer />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
