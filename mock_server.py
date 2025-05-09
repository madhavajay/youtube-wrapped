from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/login", response_class=HTMLResponse)
async def login_form():
    return """
    <html>
        <body>
            <h2>Login</h2>
            <form method="POST" action="/login">
                <input type="password" name="password" placeholder="Enter password">
                <input type="submit" value="Login">
            </form>
        </body>
    </html>
    """

@app.post("/login")
async def handle_login(password: str = Form(...)):
    if password == "secret":
        resp = RedirectResponse(url="/secure", status_code=302)
        resp.set_cookie(
            key="session_id",
            value="abc123",
            httponly=True,
            max_age=86400,  # 1 day
        )
        return resp
    return HTMLResponse("<h2>Wrong password</h2><a href='/login'>Try again</a>", status_code=401)

@app.get("/secure", response_class=HTMLResponse)
async def secure_page(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id == "abc123":
        return """
        <html>
            <body>
                <h1>🔐 You are logged in!</h1>
                <a href="/logout">Logout</a>
            </body>
        </html>
        """
    return RedirectResponse(url="/login")

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login")
    resp.delete_cookie(key="session_id")
    return resp
