import React, { useState, useEffect, useRef } from 'react';

const CalendarIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#374151" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
    <line x1="16" y1="2" x2="16" y2="6"></line>
    <line x1="8" y1="2" x2="8" y2="6"></line>
    <line x1="3" y1="10" x2="21" y2="10"></line>
  </svg>
);

const FilterIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#374151" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
  </svg>
);

const PRESETS = [
  { id: 'today', label: 'Hôm nay', days: 0 },
  { id: 'yesterday', label: 'Hôm qua', days: 1, exact: true },
  { id: '24h', label: '24 giờ qua', days: 1 },
  { id: '48h', label: '48 giờ qua', days: 2 },
  { id: '7d', label: '7 ngày qua', days: 7 },
  { id: '14d', label: '14 ngày qua', days: 14 },
  { id: '30d', label: '30 ngày qua', days: 30 },
  { id: '90d', label: '90 ngày qua', days: 90 },
  { id: '180d', label: '180 ngày qua', days: 180 },
  { id: 'all', label: 'Toàn thời gian', days: null }
];

const getPresetDates = (presetId) => {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const end = new Date(now);
  
  const preset = PRESETS.find(p => p.id === presetId);
  if (!preset || preset.days === null) return { start: null, end: null };

  const start = new Date(now);
  if (preset.exact) {
    start.setDate(now.getDate() - preset.days);
    end.setDate(now.getDate() - preset.days);
  } else {
    start.setDate(now.getDate() - preset.days);
  }
  return { start, end };
};

const formatDate = (date) => {
  if (!date) return '';
  const d = date.getDate().toString().padStart(2, '0');
  const m = (date.getMonth() + 1).toString().padStart(2, '0');
  const y = date.getFullYear();
  return `${d}/${m}/${y}`;
};

const parseDate = (str) => {
  const parts = str.split('/');
  if (parts.length === 3) {
    const d = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10) - 1;
    const y = parseInt(parts[2], 10);
    const date = new Date(y, m, d);
    if (date.getDate() === d && date.getMonth() === m && date.getFullYear() === y) {
      return date;
    }
  }
  return null;
};

export default function DateRangeFilter({ onApply }) {
  const [open, setOpen] = useState(false);
  const [preset, setPreset] = useState('all');
  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [hovered, setHovered] = useState(null);
  
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth());
  
  const [applied, setApplied] = useState('Toàn thời gian');
  
  const [inputStart, setInputStart] = useState('');
  const [inputEnd, setInputEnd] = useState('');
  
  const dropdownRef = useRef(null);
  const [isMobileScreen, setIsMobileScreen] = useState(false);

  useEffect(() => {
    setIsMobileScreen(window.innerWidth < 600);
    const handleResize = () => {
      setIsMobileScreen(window.innerWidth < 600);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (open) {
      setInputStart(formatDate(start));
      setInputEnd(formatDate(end));
      if (start) {
        setYear(start.getFullYear());
        setMonth(start.getMonth());
      } else {
        const now = new Date();
        setYear(now.getFullYear());
        setMonth(now.getMonth());
      }
    }
  }, [open, start, end]);

  const handleApply = () => {
    let newLabel = 'Tùy chỉnh';
    if (preset) {
      const p = PRESETS.find(x => x.id === preset);
      if (p) newLabel = p.label;
    } else if (start && end) {
      newLabel = `${formatDate(start)} - ${formatDate(end)}`;
    } else if (start) {
      newLabel = `Từ ${formatDate(start)}`;
    }
    
    setApplied(newLabel);
    setOpen(false);
    if (onApply) {
      onApply({ preset, start, end });
    }
  };

  const handlePresetClick = (pid) => {
    setPreset(pid);
    const dates = getPresetDates(pid);
    setStart(dates.start);
    setEnd(dates.end);
    setInputStart(formatDate(dates.start));
    setInputEnd(formatDate(dates.end));
  };

  const handleDayClick = (d) => {
    setPreset(null);
    if (!start || (start && end)) {
      setStart(d);
      setEnd(null);
      setInputStart(formatDate(d));
      setInputEnd('');
    } else {
      if (d < start) {
        setEnd(start);
        setStart(d);
        setInputStart(formatDate(d));
        setInputEnd(formatDate(start));
      } else {
        setEnd(d);
        setInputEnd(formatDate(d));
      }
    }
  };

  const handleDayHover = (d) => {
    if (start && !end) {
      setHovered(d);
    } else {
      setHovered(null);
    }
  };

  const nextMonth = () => {
    if (month === 11) {
      setMonth(0);
      setYear(year + 1);
    } else {
      setMonth(month + 1);
    }
  };

  const prevMonth = () => {
    if (month === 0) {
      setMonth(11);
      setYear(year - 1);
    } else {
      setMonth(month - 1);
    }
  };

  const handleInputStartBlur = () => {
    const d = parseDate(inputStart);
    if (d) {
      setStart(d);
      setPreset(null);
      if (end && d > end) setEnd(null);
    } else {
      setInputStart(formatDate(start));
    }
  };

  const handleInputEndBlur = () => {
    const d = parseDate(inputEnd);
    if (d) {
      if (start && d < start) {
        setInputEnd(formatDate(end));
      } else {
        setEnd(d);
        setPreset(null);
      }
    } else {
      setInputEnd(formatDate(end));
    }
  };

  // Generate calendar days
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const days = [];
  for (let i = 0; i < firstDay; i++) days.push(null);
  for (let i = 1; i <= daysInMonth; i++) days.push(new Date(year, month, i));

  return (
    <div style={{ position: 'relative', display: 'inline-block', fontFamily: 'system-ui, -apple-system, sans-serif' }} ref={dropdownRef}>
      
      {/* TRIGGER BUTTON */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button 
          onClick={() => setOpen(!open)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            background: '#fff', color: '#374151', fontSize: '14px', fontWeight: 500,
            padding: '8px 14px', borderRadius: '8px', border: '1.5px solid #e5e7eb',
            cursor: 'pointer', outline: 'none',
            boxShadow: open ? '0 0 0 2px #111827' : 'none',
            transition: 'all 0.15s ease'
          }}
        >
          <CalendarIcon />
          {applied}
        </button>
      </div>

      {/* DROPDOWN PANEL */}
      {open && (
        <div style={{
          position: 'absolute', 
          top: '100%', 
          right: isMobileScreen ? '50%' : 0, 
          transform: isMobileScreen ? 'translateX(50%)' : 'none',
          marginTop: '8px', 
          zIndex: 999,
          background: '#fff', 
          borderRadius: '14px', 
          border: '1px solid #e5e7eb',
          boxShadow: '0 8px 32px rgba(0,0,0,0.12)', 
          display: 'flex',
          flexDirection: isMobileScreen ? 'column' : 'row',
          overflow: 'hidden', 
          minWidth: isMobileScreen ? '290px' : '550px',
          width: isMobileScreen ? '90vw' : 'auto',
          maxWidth: isMobileScreen ? '340px' : 'none'
        }}>
          
          {/* CỘT TRÁI - PRESET LIST */}
          <div style={{ 
            width: isMobileScreen ? '100%' : '180px', 
            borderRight: isMobileScreen ? 'none' : '1px solid #f3f4f6', 
            borderBottom: isMobileScreen ? '1px solid #f3f4f6' : 'none',
            padding: isMobileScreen ? '8px 4px' : '10px 0',
            display: isMobileScreen ? 'flex' : 'block',
            overflowX: isMobileScreen ? 'auto' : 'visible',
            whiteSpace: isMobileScreen ? 'nowrap' : 'normal',
            scrollbarWidth: 'none', // Ẩn scrollbar trên Firefox
            msOverflowStyle: 'none'  // Ẩn scrollbar trên IE/Edge
          }}>
            {/* Ẩn scrollbar trên Webkit (Chrome/Safari) */}
            <style dangerouslySetInnerHTML={{__html: `
              div::-webkit-scrollbar { display: none !important; }
            `}} />
            {PRESETS.map(p => (
              <div 
                key={p.id}
                onClick={() => handlePresetClick(p.id)}
                onMouseEnter={(e) => { if (preset !== p.id && !isMobileScreen) e.currentTarget.style.background = '#f9fafb' }}
                onMouseLeave={(e) => { if (preset !== p.id && !isMobileScreen) e.currentTarget.style.background = 'transparent' }}
                style={{
                  padding: isMobileScreen ? '6px 12px' : '9px 20px', 
                  fontSize: isMobileScreen ? '12px' : '14px', 
                  cursor: 'pointer',
                  color: preset === p.id ? (isMobileScreen ? '#fff' : '#111827') : '#4b5563',
                  fontWeight: preset === p.id ? 700 : 400,
                  background: preset === p.id ? (isMobileScreen ? '#111827' : '#f3f4f6') : 'transparent',
                  borderRadius: isMobileScreen ? '999px' : '0',
                  margin: isMobileScreen ? '0 4px' : '0',
                  display: isMobileScreen ? 'inline-block' : 'block',
                  transition: 'all 0.1s ease',
                  flexShrink: 0
                }}
              >
                {p.label}
              </div>
            ))}
          </div>

          {/* CỘT PHẢI - CALENDAR */}
          <div style={{ 
            padding: isMobileScreen ? '12px' : '20px', 
            display: 'flex', 
            flexDirection: 'column', 
            width: '100%',
            boxSizing: 'border-box'
          }}>
            
            {/* Header điều hướng tháng */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <button 
                onClick={prevMonth}
                style={{ width: '28px', height: '28px', border: '1px solid #e5e7eb', borderRadius: '6px', background: '#fff', cursor: 'pointer', color: '#374151', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                ‹
              </button>
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                <select 
                  value={month} 
                  onChange={e => setMonth(parseInt(e.target.value))}
                  style={{ border: '1px solid #e5e7eb', borderRadius: '6px', padding: '4px 6px', fontSize: isMobileScreen ? '12px' : '14px', fontWeight: 600, color: '#111827', outline: 'none', cursor: 'pointer', background: '#fff' }}
                >
                  {Array.from({ length: 12 }).map((_, i) => (
                    <option key={i} value={i}>Tháng {i + 1}</option>
                  ))}
                </select>
                <select 
                  value={year} 
                  onChange={e => setYear(parseInt(e.target.value))}
                  style={{ border: '1px solid #e5e7eb', borderRadius: '6px', padding: '4px 6px', fontSize: isMobileScreen ? '12px' : '14px', fontWeight: 600, color: '#111827', outline: 'none', cursor: 'pointer', background: '#fff' }}
                >
                  {Array.from({ length: 21 }).map((_, i) => {
                    const y = new Date().getFullYear() - 10 + i;
                    return <option key={y} value={y}>{y}</option>
                  })}
                </select>
              </div>
              <button 
                onClick={nextMonth}
                style={{ width: '28px', height: '28px', border: '1px solid #e5e7eb', borderRadius: '6px', background: '#fff', cursor: 'pointer', color: '#374151', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                ›
              </button>
            </div>

            {/* Header ngày trong tuần */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', marginBottom: '6px' }}>
              {['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'].map(d => (
                <div key={d} style={{ fontSize: '11px', color: '#9ca3af', fontWeight: 500, textAlign: 'center' }}>{d}</div>
              ))}
            </div>

            {/* Ô ngày */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', flex: 1 }} onMouseLeave={() => setHovered(null)}>
              {days.map((d, i) => {
                if (!d) return <div key={`empty-${i}`} />;
                
                const isStart = start && d.getTime() === start.getTime();
                const isEnd = end && d.getTime() === end.getTime();
                const isSelected = isStart || isEnd;
                
                let inRange = false;
                if (start && end && d > start && d < end) inRange = true;
                if (start && !end && hovered && d > start && d <= hovered) inRange = true;
                if (start && !end && hovered && d < start && d >= hovered) inRange = true; // backward hover

                let bg = 'transparent';
                let color = '#111827';
                let br = '8px';
                let fw = 400;

                if (isSelected) {
                  bg = '#111827';
                  color = '#fff';
                  fw = 600;
                  if (start && end) {
                    if (isStart) br = '8px 0 0 8px';
                    if (isEnd) br = '0 8px 8px 0';
                    if (isStart && isEnd) br = '8px'; // same day
                  }
                } else if (inRange) {
                  bg = '#f3f4f6';
                  br = '0';
                }

                return (
                  <div 
                    key={i}
                    onClick={() => handleDayClick(d)}
                    onMouseEnter={() => handleDayHover(d)}
                    style={{
                      width: isMobileScreen ? '28px' : '34px', 
                      height: isMobileScreen ? '28px' : '34px', 
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: isMobileScreen ? '12px' : '14px', cursor: 'pointer',
                      background: bg, color: color, borderRadius: br, fontWeight: fw,
                      margin: '0 auto'
                    }}
                  >
                    {d.getDate()}
                  </div>
                );
              })}
            </div>

            {/* INPUT NGÀY VÀ NÚT ÁP DỤNG */}
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              marginTop: '16px', 
              gap: '6px', 
              flexWrap: 'nowrap',
              justifyContent: 'space-between',
              width: '100%'
            }}>
              <input 
                value={inputStart}
                onChange={e => setInputStart(e.target.value)}
                onBlur={handleInputStartBlur}
                placeholder="dd/mm/yyyy"
                style={{ 
                  flex: '1 1 auto', 
                  minWidth: '60px', 
                  maxWidth: isMobileScreen ? '85px' : '105px', 
                  border: '1.5px solid #e5e7eb', 
                  borderRadius: '8px', 
                  padding: isMobileScreen ? '6px 8px' : '8px 10px', 
                  fontSize: '12px', 
                  textAlign: 'center', 
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
              <span style={{ color: '#9ca3af', flexShrink: 0 }}>-</span>
              <input 
                value={inputEnd}
                onChange={e => setInputEnd(e.target.value)}
                onBlur={handleInputEndBlur}
                placeholder="dd/mm/yyyy"
                style={{ 
                  flex: '1 1 auto', 
                  minWidth: '60px', 
                  maxWidth: isMobileScreen ? '85px' : '105px', 
                  border: '1.5px solid #e5e7eb', 
                  borderRadius: '8px', 
                  padding: isMobileScreen ? '6px 8px' : '8px 10px', 
                  fontSize: '12px', 
                  textAlign: 'center', 
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
              <button 
                onClick={handleApply}
                onMouseEnter={e => { if(!isMobileScreen) e.currentTarget.style.background = '#374151' }}
                onMouseLeave={e => { if(!isMobileScreen) e.currentTarget.style.background = '#111827' }}
                style={{
                  flexShrink: 0, 
                  background: '#111827', 
                  color: '#fff', 
                  border: 'none',
                  borderRadius: '8px', 
                  padding: isMobileScreen ? '8px 12px' : '9px 16px', 
                  fontSize: '12px', 
                  fontWeight: 600,
                  cursor: 'pointer', 
                  transition: 'background 0.15s', 
                  whiteSpace: 'nowrap'
                }}
              >
                Áp dụng
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
