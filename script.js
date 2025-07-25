// 【‼️請務必修改此處‼️】
// 請將下方的佔位符文字 'YOUR_RENDER_URL_HERE'，
// 完整替換成您真實的 Render 後端網址。
const BACKEND_URL = 'https://su-hua-dashboard.onrender.com';

// --- 以下程式碼不需要修改 ---

document.addEventListener('DOMContentLoaded', () => {

  const updateBtn = document.getElementById('updateBtn');
  const lastUpdateElement = document.getElementById('lastUpdate');
  const rainList = document.getElementById('rain-list');
  const radarImage = document.getElementById('radar-image');
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
      if (!response.ok) {
        throw new Error(`HTTP 錯誤！ 狀態: ${response.status}`);
      }
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

    // 更新雷達圖
    radarImage.src = BACKEND_URL + '/api/radar-image';
    radarImage.onerror = () => { radarImage.alt = '雷達圖載入失敗'; };

    // 更新雨量資訊
    rainList.innerHTML = '';
    if (data.rainInfo && data.rainInfo.length > 0) {
      data.rainInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `${item.location}：<span class="rain-mm ${item.class}">${item.mm} mm</span> ${item.level} <span class="data-time">（${item.time}）</span>`;
        rainList.appendChild(li);
      });
    }

    // 更新地震資訊
    earthquakeList.innerHTML = '';
    if (data.earthquakeInfo && data.earthquakeInfo.length > 0) {
      data.earthquakeInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `<strong>${item.time}</strong>　
                        震央：${item.location}　
                        規模：${item.magnitude}　
                        深度：${item.depth}km　
                        花蓮縣：${item.hualien_level}級　
                        宜蘭縣：${item.yilan_level}級　
                        <span class="data-time">（${item.data_time}）</span>`;
        earthquakeList.appendChild(li);
      });
    }

    // 更新蘇花路況
    roadList.innerHTML = '';
     if (data.roadInfo && data.roadInfo.length > 0) {
      data.roadInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `${item.section}：<span class="road-status ${item.class}">${item.status}</span> ${item.desc} <span class="data-time">（${item.time}）</span>`;
        roadList.appendChild(li);
      });
    }

    // 更新颱風動態
    if (data.typhoonInfo) {
      typhoonBox.style.display = 'block';
      typhoonBox.innerHTML = `<div><b>${data.typhoonInfo.name}</b></div>
                            <div>${data.typhoonInfo.warning_type}｜更新時間：${data.typhoonInfo.update_time}</div>
                            <div>中心位置：${data.typhoonInfo.location}　最大風速：${data.typhoonInfo.wind_speed}</div>
                            <div>警報狀態：${data.typhoonInfo.status}</div>
                            <div><img src="${data.typhoonInfo.img_url}" alt="颱風路徑圖" width="100%"></div>`;
    } else {
      typhoonBox.style.display = 'none';
      typhoonBox.innerHTML = '目前無颱風警報';
    }
  }

  // 頁面一載入，就立刻執行一次，獲取真實資料
  fetchDataAndUpdateDashboard();
});
