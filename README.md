# DarijaDoc

Arabic/Darija Voice Medical Navigator for the GOMYCODE hackathon.
#video real demo testing



https://github.com/user-attachments/assets/383fe8b6-223a-4553-8e86-0c5628adba49


## Backend

One API process in [`Backend/`](Backend/) serves both codebases. The React app uses `/explain`, `/chat`, `/voice`, and `/location`. The Darija prompt bench from [`darijadoc-ai/`](darijadoc-ai/) is mounted on the same server: `/` is its test page, and `/api/ask`, `/api/rx`, `/api/tts`, `/api/pharmacies`, `/api/hospitals`, and `/api/cities` are its routes. Do not start `darijadoc-ai/serve.py` at the same time; it wants port 8000 too.

```sh
cd Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `Backend/.env` with `OPENAI_API_KEY`. Leave `DATABASE_URL` unset so the API uses the local SQLite file. The checked-in `.env.example` is the Docker Compose variant and points `DATABASE_URL` at Postgres. Then:

```sh
uvicorn main:app --reload --port 8000
```

## Frontend

The React application lives in [`FrontEnd/`](FrontEnd/).

```sh
cd FrontEnd
npm install
npm run dev
```

For validation, run `npm test` and `npm run build` from `FrontEnd/`.

- [Frontend setup and features](FrontEnd/README.md)
- [Backend integration contract](FrontEnd/BACKEND_CONTRACT.md)
- [UI architecture and design decisions](FrontEnd/DESIGN.md)
