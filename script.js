// 【‼️請務必修改此處‼️】
const BACKEND_URL = 'https://su-hua-dashboard.onrender.com';

// --- 以下程式碼不需要修改 ---

document.addEventListener('DOMContentLoaded', () => {

  const updateBtn = document.getElementById('updateBtn');
  const lastUpdateElement = document.getElementById('lastUpdate');
  const rainList = document.getElementById('rain-list');
  const radarImage = document.getElementById('radar-image');
  const rainfallMapImage = document.getElementById('rainfall-map-image');
  const earthquakeList = document.getElementById('earthquake-list');
  const roadList = document.getElementById('road-list');
  const typhoonBox = document.getElementById('typhoon-box');

  updateBtn.addEventListener('click', () => {
    alert('已送出立即更新指令，資料將於1分鐘內刷新！');
    fetchDataAndUpdateDashboard();
  });

  async function fetchDataAndUpdateDashboard() {
    console.log("正在從後端獲取最新資料...");
    lastUpdateElement.textContent = '資料最後更新時間：讀取中...';
    if (BACKEND_URL === 'YOUR_RENDER_URL_HERE' || !BACKEND_URL) {
      alert('錯誤：後端網址尚未在 script.js 中設定！');
      lastUpdateElement.textContent = '錯誤：後端網址尚未設定';
      return;
    }
    try {
      const response = await fetch(BACKEND_URL + '/api/dashboard-data');
      if (!response.ok) { throw new Error(`HTTP 錯誤！ 狀態: ${response.status}`); }
      const data = await response.json();
      updateDashboard(data);
    } catch (error) {
      console.error("無法獲取儀表板資料:", error);
      alert("無法連接後端伺服器，資料讀取失敗！請檢查後端服務是否正常運作，以及前端網址設定是否正確。");
      lastUpdateElement.textContent = '資料讀取失敗';
    }
  }

  function updateDashboard(data) {
    lastUpdateElement.textContent = `資料最後更新時間：${data.lastUpdate}`;
    radarImage.src = BACKEND_URL + '/api/radar-image';
    radarImage.onerror = () => { radarImage.alt = '雷達圖載入失敗'; };
    rainfallMapImage.src = BACKEND_URL + '/api/rainfall-map';
    rainfallMapImage.onerror = () => { rainfallMapImage.alt = '累積雨量圖載入失敗'; };

    rainList.innerHTML = '';
    if (data.rainInfo && data.rainInfo.length > 0) {
      data.rainInfo.forEach(item => {
        const li = document.createElement('li');
        let display_mm = ''; let display_level = item.level;
        if (item.mm === "N/A") { display_mm = ''; }
        else if (parseFloat(item.mm) === 0) { display_mm = '0 mm'; display_level = '過去 24 小時無降雨'; }
        else { display_mm = `${item.mm} mm`; }
        const time_display = item.time ? `（${item.time}）` : '';
        li.innerHTML = `${item.location}：<span class="rain-mm ${item.class}">${display_mm}</span> ${display_level} <span class="data-time">${time_display}</span>`;
        rainList.appendChild(li);
      });
    }

    earthquakeList.innerHTML = '';
    if (data.earthquakeInfo && data.earthquakeInfo.length > 0) {
      data.earthquakeInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `<strong>${item.time}</strong>　
                        震央：${item.location}　規模：${item.magnitude}　深度：${item.depth}km　
                        花蓮縣：${item.hualien_level}級　宜蘭縣：${item.yilan_level}級　
                        <span class="data-time">${item.data_time ? `（${item.data_time}）` : ''}</span>`;
        earthquakeList.appendChild(li);
      });
    } else {
      const li = document.createElement('li');
      li.textContent = '過去 72 小時內蘇花沿線無顯著有感地震。';
      earthquakeList.appendChild(li);
    }

    roadList.innerHTML = '';
     if (data.roadInfo && data.roadInfo.length > 0) {
      data.roadInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `${item.section}：<span class="road-status ${item.class}">${item.status}</span> ${item.desc} <span class="data-time">${item.time ? `（${item.time}）` : ''}</span>`;
        roadList.appendChild(li);
      });
    }

    if (data.typhoonInfo) {
      typhoonBox.style.background = '#f3f4f6';
      typhoonBox.innerHTML = `<div><b>${data.typhoonInfo.name}</b></div>
                            <div>${data.typhoonInfo.warning_type}｜更新時間：${data.typhoonInfo.update_time}</div>
                            <div>中心位置：${data.typhoonInfo.location}　最大風速：${data.typhoonInfo.wind_speed}</div>
                            <div>警報狀態：${data.typhoonInfo.status}</div>
                            <div><img src="${data.typhoonInfo.img_url}" alt="颱風路徑圖" width="100%"></div>`;
    } else {
      typhoonBox.style.background = 'none';
      typhoonBox.innerHTML = '目前暫無颱風警報';
    }
  }

  fetchDataAndUpdateDashboard();
});
