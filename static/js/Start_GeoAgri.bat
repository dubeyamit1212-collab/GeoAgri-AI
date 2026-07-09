@echo off
title GeoAgri AI

call C:\Users\amitd\miniconda3\Scripts\activate.bat amit_env

cd /d "C:\Users\amitd\Downloads\files(7)"

start "GeoAgri Server" cmd /k "python -m uvicorn main:app --reload --port 8001"

timeout /t 8 /nobreak >nul

start "" "http://127.0.0.1:8001/viewer"