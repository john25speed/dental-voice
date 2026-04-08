"""Dental Voice — локальный сервер с Whisper STT + GPT-парсер."""
import os
import json
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
import tempfile
from openai import OpenAI

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

PARSE_SYSTEM = """Ты — парсер стоматологических команд. Из текста врача извлеки данные о зубах.

Верни ТОЛЬКО JSON:
{
  "teeth": [
    {"num": 5, "jaw": "upper", "side": "right", "code": "С", "clear": false}
  ],
  "mucosa": null
}

Коды диагнозов (используй РОВНО эти символы):
- О — отсутствует (удалён, нет зуба)
- R — корень
- С — кариес
- Р — пульпит
- Pt — периодонтит
- П — пломба
- К — коронка
- И — имплант / искусственный
- А I — пародонтит I степени
- А II — пародонтит II степени
- А III — пародонтит III степени

Правила:
- num: число от 1 до 8
- jaw: "upper" (верхняя) или "lower" (нижняя)
- side: "right" (правая) или "left" (левая)
- Если врач говорит "очистить/стереть/убрать" — clear: true, code: ""
- Если текст про слизистую/дёсны/нёбо — {"teeth": [], "mucosa": "текст как есть"}
- Врач может назвать несколько зубов за раз — верни массив
- Если не удалось распознать — {"teeth": [], "error": "не распознано"}
- Не додумывай. Если челюсть или сторона не указана — НЕ добавляй зуб, верни error.

Формулировки отсутствия зуба (код О):
- "нет", "нету", "отсутствует", "удалён", "удален", "первого нет", "пятёрки нет" — всё это код О.
- "первого нет" = зуб 1, код О. "шестёрки нет" = зуб 6, код О.

Формулировки номеров зубов:
- "первый/первого/первая" = 1, "двойка" = 2, "тройка" = 3, "четвёрка" = 4
- "пятёрка" = 5, "шестёрка" = 6, "семёрка" = 7, "восьмёрка" = 8

Пример: "восьмёрка нижняя правая отсутствует, семёрка пародонтит, шестёрка пломба, пятёрка периодонтит, четвёрка пульпит, тройка кариес, двойка корень, первого нет"
→ 8 зубов, все нижние правые, коды: О, А I, П, Pt, Р, С, R, О."""


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/health')
def health():
    key = os.getenv('OPENAI_API_KEY', '')
    # Тест связи с OpenAI
    api_ok = False
    api_error = None
    try:
        r = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': 'say ok'}],
            max_tokens=3,
        )
        api_ok = True
    except Exception as e:
        api_error = f'{type(e).__name__}: {e}'
    return jsonify({
        'status': 'ok',
        'key_set': bool(key),
        'key_prefix': key[:12] + '...' if key else 'NOT SET',
        'api_ok': api_ok,
        'api_error': api_error,
    })


@app.route('/transcribe', methods=['POST'])
def transcribe():
    if 'audio' not in request.files:
        return jsonify({'error': 'no audio'}), 400

    audio = request.files['audio']
    tmp_path = os.path.join(tempfile.gettempdir(), 'dental_voice_tmp.webm')
    audio.save(tmp_path)

    try:
        with open(tmp_path, 'rb') as f:
            result = client.audio.transcriptions.create(
                model='whisper-1',
                file=f,
                language='ru',
            )
        return jsonify({'text': result.text})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'type': type(e).__name__}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.route('/parse', methods=['POST'])
def parse():
    text = request.json.get('text', '')
    mode = request.json.get('mode', 'single')
    if not text.strip():
        return jsonify({'error': 'no text'}), 400

    mode_instruction = (
        "\n\nРЕЖИМ: ОДИН ЗУБ. Верни ТОЛЬКО один зуб (первый упомянутый). Если упомянуто несколько — бери первый, остальные игнорируй."
        if mode == 'single' else
        "\n\nРЕЖИМ: ПАЧКА. Верни ВСЕ упомянутые зубы в массиве."
    )

    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PARSE_SYSTEM + mode_instruction},
                {"role": "user", "content": text},
            ],
            temperature=0,
        )
        result = json.loads(response.choices[0].message.content)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print('Dental Voice — http://localhost:5055')
    app.run(host='0.0.0.0', port=5055, debug=True)
