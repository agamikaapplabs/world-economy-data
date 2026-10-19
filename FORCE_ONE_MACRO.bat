@echo off
cd /d "%~dp0"
echo.
echo Valid indicator keys:
echo inflation gdp_growth gdp_usd gdp_per_capita unemployment reserves_usd
echo import_cover exports_usd exports_gdp imports_usd imports_gdp trade_balance
echo current_account_usd current_account_gdp gov_debt_gdp fiscal_balance_gdp
echo external_debt_gni fdi_usd energy_imports_pct energy_use_pc electricity_pc
echo agriculture_gdp food_exports_pct food_imports_pct ores_metals_exports_pct
echo fuel_exports_pct fuel_imports_pct container_port_teu
echo.
set /p INDKEY=Indicator key to force refresh: 
if "%INDKEY%"=="" exit /b 0
python fetch_macro.py --force "%INDKEY%"
pause
