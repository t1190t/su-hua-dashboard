// 等待整個網頁的 HTML 結構都載入完成後，再執行裡面的程式碼
document.addEventListener('DOMContentLoaded', () => {

  // 找到「立即更新」按鈕
  const updateBtn = document.getElementById('updateBtn');

  // 為按鈕加上點擊事件
  updateBtn.addEventListener('click', () => {
    alert('已送出立即更新指令，資料將於1分鐘內自動刷新。請稍後手動重新整理網頁以查看最新資料！');
    // 這裡未來會呼叫後端 API 來觸發更新
    fetchDataAndUpdateDashboard();
  });

  // --- 函式定義區 ---

  // 主要功能：從後端取得所有資料並更新整個儀表板
  function fetchDataAndUpdateDashboard() {
    console.log("正在從後端獲取最新資料...");
    // 未來這裡會寫 fetch('後端程式的網址') 來取得真實資料
    // 現在，我們先用您設計的假資料來模擬
    const fakeData = getFakeData();
    updateDashboard(fakeData);
  }

  // 更新整個儀表板的資料
  function updateDashboard(data) {
    // 更新「最後更新時間」
    document.getElementById('lastUpdate').textContent = `資料最後更新時間：${data.lastUpdate}`;

    // 更新雨量資訊
    const rainList = document.getElementById('rain-list');
    rainList.innerHTML = ''; // 先清空列表
    data.rainInfo.forEach(item => {
      const li = document.createElement('li');
      li.innerHTML = `${item.location}：<span class="rain-mm ${item.class}">${item.mm} mm</span> ${item.level} <span class="data-time">（${item.time}）</span>`;
      rainList.appendChild(li);
    });

    // 更新雷達回波圖
    document.getElementById('radar-image').src = data.radarImgUrl;

    // 更新地震資訊
    const earthquakeList = document.getElementById('earthquake-list');
    earthquakeList.innerHTML = ''; // 先清空列表
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

    // 更新蘇花路況
    const roadList = document.getElementById('road-list');
    roadList.innerHTML = ''; // 先清空列表
    data.roadInfo.forEach(item => {
      const li = document.createElement('li');
      li.innerHTML = `${item.section}：<span class="road-status ${item.class}">${item.status}</span> ${item.desc} <span class="data-time">（${item.time}）</span>`;
      roadList.appendChild(li);
    });

    // 更新颱風動態
    const typhoonBox = document.getElementById('typhoon-box');
    if (data.typhoonInfo) {
      typhoonBox.innerHTML = `<div><b>${data.typhoonInfo.name}</b></div>
                            <div>${data.typhoonInfo.warning_type}｜更新時間：${data.typhoonInfo.update_time}</div>
                            <div>中心位置：${data.typhoonInfo.location}　最大風速：${data.typhoonInfo.wind_speed}</div>
                            <div>警報狀態：${data.typhoonInfo.status}</div>
                            <div><img src="${data.typhoonInfo.img_url}" alt="颱風路徑圖" width="100%"></div>`;
    } else {
      typhoonBox.innerHTML = '目前無颱風警報';
    }
  }

  // 模擬從後端收到的資料 (使用您設計的範例)
  function getFakeData() {
    return {
      lastUpdate: "2025-07-24 10:45",
      rainInfo: [
        { location: "蘇澳鎮", mm: 108, class: "rain-yellow", level: "🟨 大雨", time: "10:30" },
        { location: "南澳鄉", mm: 68, class: "rain-blue", level: "🟦 中雨", time: "10:30" },
        { location: "秀林鄉", mm: 26, class: "rain-green", level: "🟩 小雨", time: "10:30" },
        { location: "新城鄉", mm: 75, class: "rain-blue", level: "🟦 中雨", time: "10:30" },
      ],
      radarImgUrl: "https://www.cwa.gov.tw/Data/radar/CV1_3600.png",
      earthquakeInfo: [
        { time: "2025-07-24 08:21", location: "花蓮縣近海", magnitude: 4.8, depth: 12, hualien_level: 3, yilan_level: 2, data_time: "08:25" },
        { time: "2025-07-23 22:18", location: "宜蘭縣蘇澳", magnitude: 4.3, depth: 9, hualien_level: 1, yilan_level: 3, data_time: "22:22" }
      ],
      roadInfo: [
        { section: "蘇澳-南澳", status: "正常通行", class: "road-green", desc: "", time: "10:30" },
        { section: "南澳-和平", status: "預警中", class: "road-yellow", desc: "（零星落石，機具巡查）", time: "10:30" },
        { section: "和平-秀林", status: "正常通行", class: "road-green", desc: "", time: "10:30" }
      ],
      typhoonInfo: {
        name: "2025年第7號颱風 杜鵑（Dujuan）",
        warning_type: "海上颱風警報",
        update_time: "10:00",
        location: "北緯23.5°，東經128.7°",
        wind_speed: "每秒44公尺",
        status: "發布海上警報，影響台灣東北部",
        img_url: "https://www.cwa.gov.tw/Data/typhoon/TY_NEWS/TY_NEWS_0.jpg"
      }
    };
  }

  // --- 程式執行入口 ---
  // 頁面一載入，就先執行一次，用假資料填滿儀表板
  fetchDataAndUpdateDashboard();
});