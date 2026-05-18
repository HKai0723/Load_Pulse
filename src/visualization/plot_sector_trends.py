import pandas as pd
import plotly.graph_objects as go
import os

# 1. 設定路徑
csv_path = r"C:\school\Load_Pulse\Denmark\Clean_Consumption_Wide.csv"
output_html = r"C:\school\Load_Pulse\Denmark\plot\Sector_Trends_LineChart.html"

print("📊 正在載入並處理 5 年的電力資料...")
df = pd.read_csv(csv_path)

# 將時間設為 Index，這是進行「時間序列重採樣」的必備動作
df['TimeUTC'] = pd.to_datetime(df['TimeUTC'])
df.set_index('TimeUTC', inplace=True)

# 2. 資料降頻：從「每小時 (Hourly)」轉成「每日平均 (Daily)」
# 這會把 4 萬多筆資料濃縮成 1,826 筆，讓圖表瞬間變得極度流暢且趨勢明顯
print("⏳ 正在計算每日平均用電量 (Daily Resampling)...")
df_daily = df[['load_business', 'load_public', 'load_private']].resample('D').mean()

# 3. 繪製互動式折線圖 (使用 Plotly Graph Objects 以獲得最高效能)
print("🎨 正在生成 Plotly 互動圖表...")
fig = go.Figure()

# 加入商業用電 (藍色系，通常最穩定)
fig.add_trace(go.Scatter(
    x=df_daily.index, y=df_daily['load_business'],
    mode='lines', name='商業用電 (Business)',
    line=dict(color='#1f77b4', width=1.5)
))

# 加入民生用電 (橘/紅色系，通常波動最大)
fig.add_trace(go.Scatter(
    x=df_daily.index, y=df_daily['load_private'],
    mode='lines', name='民生用電 (Private)',
    line=dict(color='#ff7f0e', width=1.5)
))

# 加入公共用電 (綠色系，通常有明顯的季節性)
fig.add_trace(go.Scatter(
    x=df_daily.index, y=df_daily['load_public'],
    mode='lines', name='公共用電 (Public)',
    line=dict(color='#2ca02c', width=1.5)
))
# #-------------------------------------------------------
# # 1. 畫出原本的每日數據 (調低透明度當背景)
# fig.add_trace(go.Scatter(
#     x=df_daily.index, y=df_daily['load_business'],
#     mode='lines', name='商業用電 (每日)',
#     line=dict(color='#1f77b4', width=1),
#     opacity=0.3  # 變半透明
# ))

# # 2. 畫出 7 天移動平均線 (平滑趨勢)
# fig.add_trace(go.Scatter(
#     x=df_daily.index, 
#     y=df_daily['load_business'].rolling(window=7).mean(), # Pandas 神器
#     mode='lines', name='商業用電 (7天均線)',
#     line=dict(color='darkblue', width=2.5) # 加粗、加深
# ))

# # 在 fig.update_layout 之前加上這段，標示出 2025 年的秋季假期
# fig.add_vrect(
#     x0="2025-10-11", x1="2025-10-19",
#     fillcolor="gray", opacity=0.2, line_width=0,
#     annotation_text="秋季假期", annotation_position="top left"
# )
#------------------------------------------------------------
# 4. 優化版面與互動控制
fig.update_layout(
    title='丹麥三大產業用電趨勢 (2021-2025 每日平均)',
    xaxis_title='時間 (年-月)',
    yaxis_title='平均用電量 (kWh)',
    hovermode='x unified',          # 讓滑鼠游標一次顯示三個產業的數值，方便比對
    legend=dict(
        orientation="h",            # 圖例改為水平顯示在圖表下方
        yanchor="bottom", y=-0.2,
        xanchor="center", x=0.5
    ),
    template='plotly_white',        # 使用乾淨的白底主題
    xaxis=dict(
        rangeselector=dict(         # 加入快速時間切換按鈕
            buttons=list([
                dict(count=1, label="1個月", step="month", stepmode="backward"),
                dict(count=6, label="半年", step="month", stepmode="backward"),
                dict(count=1, label="1年", step="year", stepmode="backward"),
                dict(step="all", label="全部 (5年)")
            ])
        ),
        rangeslider=dict(visible=True), # 開啟下方的小型時間拖曳拉桿
        type="date"
    )
)

# 5. 輸出成 HTML
fig.write_html(output_html)
print(f"✅ 圖表已成功輸出至：{output_html}")