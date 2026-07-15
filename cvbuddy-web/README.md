# CVBuddy Web

Frontend mẫu kết nối với FastAPI trong `../cvbuddy-ai`.

## Chạy local

Terminal 1 - backend:

```powershell
cd E:\Project\cvbuddy-ai
.venv-codex\Scripts\uvicorn.exe app.main:app --reload --port 8001
```

Terminal 2 - frontend:

```powershell
cd E:\Project\cvbuddy-web
E:\Project\cvbuddy-ai\.venv-codex\Scripts\python.exe -m http.server 5173
```

Mở `http://localhost:5173`.

Đổi `apiBaseUrl` trong `config.js` khi backend được deploy. Không đặt khóa Groq hoặc khóa model provider trong frontend.

Danh sách model được tải từ `GET /v1/models`. Model được chọn sẽ áp dụng cho cả AI parsing và phân tích CV.
