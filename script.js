// 等待整個網頁的 HTML 結構都載入完成後，再執行裡面的程式碼
document.addEventListener('DOMContentLoaded', () => {

  // 您的後端服務網址
  const BACKEND_URL = 'https://su-hua-dashboard.onrender.com';

  // 找到「立即更新」按鈕
  const updateBtn = document.getElementById('updateBtn');

  // 為按鈕加上點擊事件
  updateBtn.addEventListener('click', () => {
    alert('已送出立即更新指令，資料將於1分鐘內刷新！');
    fetchDataAndUpdateDashboard();
  });

  // --- 函式定義區 ---

  // 主要功能：從後端取得所有資料並更新整個儀表板
  async function fetchDataAndUpdateDashboard() {
    console.log("正在從後端獲取最新資料...");
    document.getElementById('lastUpdate').textContent = '資料最後更新時間：讀取中...';
    try {
      const response = await fetch(BACKEND_URL);
      if (!response.ok) {
        throw new Error(`HTTP 錯誤！ 狀態: ${response.status}`);
      }
      const data = await response.json();
      updateDashboard(data);
    } catch (error) {
      console.error("無法獲取儀表板資料:", error);
      alert("無法連接後端伺服器，資料讀取失敗！請稍後再試。");
    }
  }

  // 更新整個儀表板的資料
  function updateDashboard(data) {
    // 更新「最後更新時間」
    document.getElementById('lastUpdate').textContent = `資料最後更新時間：${data.lastUpdate}`;

    // 更新雨量資訊
    const rainList = document.getElementById('rain-list');
    rainList.innerHTML = ''; // 先清空列表
    if (data.rainInfo && data.rainInfo.length > 0) {
      data.rainInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `${item.location}：<span class="rain-mm ${item.class}">${item.mm} mm</span> ${item.level} <span class="data-time">（${item.time}）</span>`;
        rainList.appendChild(li);
      });
    }

    // 更新雷達回波圖
    document.getElementById('radar-image').src = data.radarImgUrl;

    // 更新地震資訊
    const earthquakeList = document.getElementById('earthquake-list');
    earthquakeList.innerHTML = ''; // 先清空列表
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
    const roadList = document.getElementById('road-list');
    roadList.innerHTML = ''; // 先清空列表
     if (data.roadInfo && data.roadInfo.length > 0) {
      data.roadInfo.forEach(item => {
        const li = document.createElement('li');
        li.innerHTML = `${item.section}：<span class="road-status ${item.class}">${item.status}</span> ${item.desc} <span class="data-time">（${item.time}）</span>`;
        roadList.appendChild(li);
      });
    }

    // 更新颱風動態
    const typhoonBox = document.getElementById('typhoon-box');
    if (data.typhoonInfo) {
      typhoonBox.style.display = 'block'; // 顯示區塊
      typhoonBox.innerHTML = `<div><b>${data.typhoonInfo.name}</b></div>
                            <div>${data.typhoonInfo.warning_type}｜更新時間：${data.typhoonInfo.update_time}</div>
                            <div>中心位置：${data.typhoonInfo.location}　最大風速：${data.typhoonInfo.wind_speed}</div>
                            <div>警報狀態：${data.typhoonInfo.status}</div>
                            <div><img src="${data.typhoonInfo.img_url}" alt="颱風路徑圖" width="100%"></div>`;
    } else {
      typhoonBox.style.display = 'none'; // 隱藏區塊
      typhoonBox.innerHTML = '目前無颱風警報';
    }
  }

  // --- 程式執行入口 ---
  // 頁面一載入，就立刻執行一次，獲取真實資料
  fetchDataAndUpdateDashboard();
});
