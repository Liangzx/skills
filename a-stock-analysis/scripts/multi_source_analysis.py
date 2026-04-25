#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用多数据源股票分析脚本
支持多个数据源库，自动故障转移
支持A股、港股、美股

用法:
    python multi_source_analysis.py [股票代码] [市场类型]
    例如:
        python multi_source_analysis.py 300752        # A股默认
        python multi_source_analysis.py 0700.HK       # 港股
        python multi_source_analysis.py AAPL          # 美股
        python multi_source_analysis.py 600519 SH     # 指定市场
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import time
import sys
warnings.filterwarnings('ignore')


class StockDataFetcher:
    """多数据源股票数据获取器"""
    
    def __init__(self, stock_code="300752", market="CN"):
        """
        初始化数据获取器
        
        Args:
            stock_code: 股票代码 (如: 300752, 0700.HK, AAPL)
            market: 市场类型 (CN=中国A股, HK=港股, US=美股)
        """
        self.stock_code = stock_code
        self.market = market.upper()
        self.data_source_used = None
        self._normalize_stock_code()
    
    def _normalize_stock_code(self):
        """标准化股票代码格式"""
        code = self.stock_code.upper()
        
        # 检测市场类型
        if '.HK' in code or (code.startswith('0') and len(code) == 4):
            self.market = 'HK'
            self.original_code = code.replace('.HK', '')
        elif code in ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META'] or ('.' not in code and len(code) <= 5 and self.market == 'US'):
            self.market = 'US'
            self.original_code = code
        else:
            self.market = 'CN'
            self.original_code = code.replace('.SS', '').replace('.SZ', '')
        
        # 设置显示名称
        self.display_name = f"{self.original_code}.{self.market}"
    
    def fetch_from_akshare(self):
        """从AKshare获取数据"""
        try:
            print(f"📡 尝试从 AKshare 获取 {self.display_name} 数据...")
            import akshare as ak
            
            if self.market == 'CN':
                # A股数据
                df = ak.stock_zh_a_hist(
                    symbol=self.original_code, 
                    period="daily", 
                    adjust="qfq"
                )
            elif self.market == 'HK':
                # 港股数据
                df = ak.stock_hk_daily(
                    symbol=self.original_code,
                    adjust="qfq"
                )
            elif self.market == 'US':
                # 美股数据
                df = ak.stock_us_hist(
                    symbol=self.original_code,
                    start_date="20230101",
                    end_date="20261231",
                    adjust="qfq"
                )
            else:
                return None
            
            if df.empty:
                return None
            
            # 重命名列以统一格式
            column_mapping = {
                '日期': 'date', 'date': 'date',
                '开盘': 'open', 'open': 'open',
                '收盘': 'close', 'close': 'close',
                '最高': 'high', 'high': 'high',
                '最低': 'low', 'low': 'low',
                '成交量': 'volume', 'volume': 'volume', '成交数量': 'volume'
            }
            
            df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
            
            # 确保必要的列存在
            required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                print(f"⚠️ AKshare 返回数据缺少必要列")
                return None
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            self.data_source_used = "AKshare"
            print(f"✅ AKshare 数据获取成功 ({len(df)}条记录)")
            return df
            
        except Exception as e:
            print(f"❌ AKshare 失败: {str(e)[:100]}")
            return None
    
    def fetch_from_tushare(self):
        """从Tushare获取数据（仅支持A股）"""
        try:
            if self.market != 'CN':
                print("⚠️ Tushare 仅支持A股，跳过")
                return None
            
            print(f"📡 尝试从 Tushare 获取 {self.display_name} 数据...")
            import tushare as ts
            
            df = ts.get_k_data(self.original_code, ktype='D')
            
            if df is None or df.empty:
                return None
            
            df = df.rename(columns={
                'date': 'date',
                'open': 'open',
                'close': 'close',
                'high': 'high',
                'low': 'low',
                'volume': 'volume'
            })
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            self.data_source_used = "Tushare"
            print(f"✅ Tushare 数据获取成功 ({len(df)}条记录)")
            return df
            
        except Exception as e:
            print(f"❌ Tushare 失败: {str(e)[:100]}")
            return None
    
    def fetch_from_baostock(self):
        """从Baostock获取数据（仅支持A股）"""
        try:
            if self.market != 'CN':
                print("⚠️ Baostock 仅支持A股，跳过")
                return None
            
            print(f"📡 尝试从 Baostock 获取 {self.display_name} 数据...")
            import baostock as bs
            
            # 登录
            lg = bs.login()
            if lg.error_code != '0':
                print(f"Baostock登录失败: {lg.error_msg}")
                return None
            
            # 转换股票代码格式 (300752 -> sz.300752, 600519 -> sh.600519)
            if self.original_code.startswith('6'):
                bs_code = f"sh.{self.original_code}"
            else:
                bs_code = f"sz.{self.original_code}"
            
            # 获取历史数据
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume",
                start_date='2023-01-01',
                end_date=datetime.now().strftime('%Y-%m-%d'),
                frequency="d",
                adjustflag="3"  # 后复权
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            bs.logout()
            
            if not data_list:
                return None
            
            df = pd.DataFrame(data_list, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            
            # 转换数据类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.dropna()
            df = df.sort_values('date').reset_index(drop=True)
            
            self.data_source_used = "Baostock"
            print(f"✅ Baostock 数据获取成功 ({len(df)}条记录)")
            return df
            
        except Exception as e:
            print(f"❌ Baostock 失败: {str(e)[:100]}")
            return None
    
    def fetch_from_pytdx(self):
        """从Pytdx获取数据（仅支持A股）"""
        try:
            if self.market != 'CN':
                print("⚠️ Pytdx 仅支持A股，跳过")
                return None
            
            print(f"📡 尝试从 Pytdx 获取 {self.display_name} 数据...")
            from pytdx.hq import TdxHq_API
            
            api = TdxHq_API()
            
            # 连接服务器
            if not api.connect('119.147.212.81', 7709):
                print("Pytdx连接失败")
                return None
            
            # 转换股票代码
            market = 0  # 0=深圳, 1=上海
            if self.original_code.startswith('6'):
                market = 1
            
            # 获取K线数据
            data = api.get_security_bars(9, market, self.original_code, 0, 800)  # 9=日K
            
            api.disconnect()
            
            if not data:
                return None
            
            # 转换为DataFrame
            df = pd.DataFrame(data)
            df = df.rename(columns={
                'datetime': 'date',
                'open': 'open',
                'close': 'close',
                'high': 'high',
                'low': 'low',
                'vol': 'volume'
            })
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            self.data_source_used = "Pytdx"
            print(f"✅ Pytdx 数据获取成功 ({len(df)}条记录)")
            return df
            
        except Exception as e:
            print(f"❌ Pytdx 失败: {str(e)[:100]}")
            return None
    
    def fetch_data(self):
        """
        按优先级尝试多个数据源
        返回: DataFrame 或 None
        """
        print("\n" + "=" * 70)
        print(f"开始获取 {self.display_name} 股票数据...")
        print("=" * 70 + "\n")
        
        # 数据源列表（按优先级）
        data_sources = [
            ("AKshare", self.fetch_from_akshare),
            ("Tushare", self.fetch_from_tushare),
            ("Baostock", self.fetch_from_baostock),
            ("Pytdx", self.fetch_from_pytdx)
        ]
        
        for source_name, fetch_func in data_sources:
            df = fetch_func()
            if df is not None and not df.empty:
                print(f"\n🎉 成功使用 {source_name} 获取数据\n")
                return df
            time.sleep(1)  # 避免频繁请求
        
        print("\n⚠️ 所有数据源均失败，将使用模拟数据\n")
        return None


def generate_sample_data(stock_code="UNKNOWN", market="CN"):
    """生成模拟数据作为最后的备选方案"""
    print(f"🔄 生成 {stock_code}.{market} 的模拟数据...\n")
    
    dates = pd.date_range(end=datetime.now(), periods=252, freq='B')
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.02, 252)
    
    # 根据不同市场设置不同的基准价格
    base_prices = {'CN': 20, 'HK': 300, 'US': 150}
    base_price = base_prices.get(market, 20)
    prices = base_price * np.cumprod(1 + returns)
    
    df = pd.DataFrame({
        'date': dates,
        'open': prices * (1 + np.random.normal(0, 0.005, 252)),
        'high': prices * (1 + np.abs(np.random.normal(0, 0.01, 252))),
        'low': prices * (1 - np.abs(np.random.normal(0, 0.01, 252))),
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 252)
    })
    
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    
    return df


def calculate_indicators(df):
    """计算技术指标"""
    
    # 均线
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA60'] = df['close'].rolling(window=60).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 布林带
    df['BOLL_MIDDLE'] = df['close'].rolling(window=20).mean()
    std_dev = df['close'].rolling(window=20).std()
    df['BOLL_UPPER'] = df['BOLL_MIDDLE'] + 2 * std_dev
    df['BOLL_LOWER'] = df['BOLL_MIDDLE'] - 2 * std_dev
    
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_DIF'] = ema12 - ema26
    df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_HIST'] = df['MACD_DIF'] - df['MACD_DEA']
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    return df


def display_analysis(df, data_source, stock_code, market):
    """显示分析结果"""
    
    latest = df.iloc[-1]
    current_price = latest['close']
    
    # 根据市场设置货币符号
    currency_symbols = {'CN': '¥', 'HK': 'HK$', 'US': '$'}
    currency = currency_symbols.get(market, '¥')
    
    display_name = f"{stock_code}.{market}"
    
    print("\n" + "=" * 70)
    print(f"  {display_name} 技术分析报告")
    print(f"  数据源: {data_source}")
    print(f"  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 价格与均线
    print("\n【价格与均线】")
    print("-" * 70)
    print(f"当前价格: {currency}{current_price:.2f}")
    print(f"MA5:  {currency}{latest['MA5']:.2f}  {'↑' if current_price > latest['MA5'] else '↓'}")
    print(f"MA20: {currency}{latest['MA20']:.2f}  {'↑' if current_price > latest['MA20'] else '↓'}")
    print(f"MA60: {currency}{latest['MA60']:.2f}  {'↑' if current_price > latest['MA60'] else '↓'}")
    
    # RSI
    print("\n【RSI指标】")
    print("-" * 70)
    rsi = latest['RSI']
    print(f"RSI(14): {rsi:.2f}")
    if rsi > 70:
        print("状态: ⚠️ 超买区")
    elif rsi < 30:
        print("状态: ✅ 超卖区")
    else:
        print("状态: ➖ 中性区")
    
    # 布林带
    print("\n【布林带 BOLL】")
    print("-" * 70)
    print(f"上轨: {currency}{latest['BOLL_UPPER']:.2f}")
    print(f"中轨: {currency}{latest['BOLL_MIDDLE']:.2f}")
    print(f"下轨: {currency}{latest['BOLL_LOWER']:.2f}")
    
    boll_width = latest['BOLL_UPPER'] - latest['BOLL_LOWER']
    price_position = (current_price - latest['BOLL_LOWER']) / boll_width * 100
    print(f"价格位置: {price_position:.1f}%")
    
    if current_price > latest['BOLL_UPPER']:
        print("信号: ⚠️ 突破上轨")
    elif current_price < latest['BOLL_LOWER']:
        print("信号: ✅ 跌破下轨")
    elif current_price > latest['BOLL_MIDDLE']:
        print("信号: 📈 中轨上方")
    else:
        print("信号: 📉 中轨下方")
    
    # MACD
    print("\n【MACD指标】")
    print("-" * 70)
    print(f"DIF: {latest['MACD_DIF']:.4f}")
    print(f"DEA: {latest['MACD_DEA']:.4f}")
    print(f"MACD柱: {latest['MACD_HIST']:.4f}")
    
    prev_hist = df['MACD_HIST'].iloc[-2] if len(df) >= 2 else 0
    if latest['MACD_DIF'] > latest['MACD_DEA']:
        print("信号: 📈 多头市场")
    else:
        print("信号: 📉 空头市场")
    
    # ATR
    print("\n【ATR波动率】")
    print("-" * 70)
    print(f"ATR(14): {currency}{latest['ATR']:.2f}")
    stop_loss = current_price - latest['ATR'] * 2
    print(f"建议止损: {currency}{stop_loss:.2f}")
    
    # 综合建议
    print("\n" + "=" * 70)
    print("【投资建议】")
    print("=" * 70)
    
    score = 0
    if rsi < 30: score += 2
    elif rsi > 70: score -= 2
    
    if latest['MACD_DIF'] > latest['MACD_DEA']: score += 1.5
    else: score -= 1.5
    
    if current_price > latest['BOLL_MIDDLE']: score += 0.5
    else: score -= 0.5
    
    if score >= 2:
        print("💡 建议: BUY (买入)")
    elif score <= -2:
        print("💡 建议: AVOID (规避)")
    else:
        print("💡 建议: HOLD (观望)")
    
    print("\n⚠️ 免责声明: 仅供参考，不构成投资建议")
    print("=" * 70 + "\n")


def main():
    """主函数"""
    # 从命令行参数获取股票代码和市场类型
    if len(sys.argv) >= 2:
        stock_code = sys.argv[1]
        market = sys.argv[2].upper() if len(sys.argv) >= 3 else "CN"
    else:
        stock_code = "300752"  # 默认隆利科技
        market = "CN"
    
    print("\n" + "=" * 70)
    print("  通用多数据源股票分析系统")
    print("  支持: A股(CN)、港股(HK)、美股(US)")
    print("  数据源: AKshare, Tushare, Baostock, Pytdx")
    print("=" * 70)
    
    # 创建数据获取器
    fetcher = StockDataFetcher(stock_code, market)
    
    # 尝试获取数据
    df = fetcher.fetch_data()
    
    # 如果所有数据源都失败，使用模拟数据
    if df is None:
        df = generate_sample_data(fetcher.original_code, fetcher.market)
        data_source = "模拟数据"
    else:
        data_source = fetcher.data_source_used
    
    # 计算指标
    df = calculate_indicators(df)
    
    # 显示分析
    display_analysis(df, data_source, fetcher.original_code, fetcher.market)


if __name__ == "__main__":
    main()
