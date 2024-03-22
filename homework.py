from http import HTTPStatus
import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
import telegram

from exceptions import HTTPStatusNotOK


EXCEPTION_ERROR = 'Сбой в работе программы: {error}'
EXCEPTION_BOT_ERROR = 'При работе бота возникла ошибка.\n{error}'
TOKENS_ERROR = 'Не валидные переменные окружения: {env_vars}!'
STATUS_VALUE_ERROR = 'Неожиданное значение ключа "status" - {status}'
RESPONSE_NOT_DICT_ERROR = (
    'Объект HTTP-ответа должен быть словарем, вместо {response_type}!'
)
HOMEWORKS_NOT_LIST_ERROR = (
    'Объект "homeworks" должен быть списком, вместо {homeworks_type}!'
)
HOMEWORKS_NOT_IN_DICT_ERROR = 'Ключ "homeworks" отсутствует в словаре!'
HOMEWORK_NAME_NOT_IN_DICT_ERROR = 'Ключ "homework_name" отсутсвует в словаре!'
JSON_ERROR = (
    'Сервер прислал ответ с ошибкой {error}'
    'Параметры запроса:\n'
    'url: {url};\n'
    'headers: {headers};\n'
    'params: {params}.'
)
RESPONSE_CODE_ERROR = (
    'Страница загружена с ошибками! Код страницы {code}.\n'
    'Параметры запроса:\n'
    'url: {url};\n'
    'headers: {headers};\n'
    'params: {params}.'
)
REQUEST_ERROR = (
    'Ошибка при подключении к странице {url}!\n'
    '{error}'
    'Параметры запроса:\n'
    'headers: {headers};\n'
    'params: {params}.'
)

STATUS_HAS_CHANGED = ('Изменился статус проверки работы '
                      '"{homework_name}". {verdict}')
STATUS_HAS_NOT_CHANGED = 'Статус проверки не изменился.'
SEND_MESSAGE_SUCCESS = 'Успешная отправка сообщения: {message}.'


load_dotenv()

ENV_VARS = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка токенов."""
    invalid_env_vars = [var for var in ENV_VARS if not globals().get(var)]
    if invalid_env_vars:
        logging.critical(TOKENS_ERROR.format(env_vars=invalid_env_vars))
        raise ValueError(TOKENS_ERROR.format(env_vars=invalid_env_vars))


def send_message(bot, message):
    """Отправка сообщения бота в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.error.TelegramError as error:
        logging.exception(error)
    else:
        logging.debug(SEND_MESSAGE_SUCCESS.format(message=message))
        return True


def get_api_answer(timestamp):
    """Выполнение API-запроса."""
    params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    try:
        response = requests.get(**params)
    except requests.RequestException as error:
        raise ConnectionError(REQUEST_ERROR.format(error=error, **params))
    response_code = response.status_code
    if response_code != HTTPStatus.OK:
        raise HTTPStatusNotOK(RESPONSE_CODE_ERROR.format(
            response_code,
            **params))
    json = response.json()
    for key in ['error', 'code']:
        if key in json:
            raise ConnectionError(
                JSON_ERROR.format(
                    error=json.get(key),
                    **params
                )
            )
    return json


def check_response(response):
    """Проверка HTTP-ответа."""
    if not isinstance(response, dict):
        raise TypeError(RESPONSE_NOT_DICT_ERROR.format(
            response_type=type(response)
        ))
    if 'homeworks' not in response:
        raise KeyError(HOMEWORKS_NOT_IN_DICT_ERROR)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(HOMEWORKS_NOT_LIST_ERROR.format(
            homeworks_type=type(homeworks)
        ))
    return response


def parse_status(homework):
    """Получение статуса проверки домашнего задания."""
    status = homework['status']
    if 'homework_name' not in homework:
        raise KeyError(HOMEWORK_NAME_NOT_IN_DICT_ERROR)
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(STATUS_VALUE_ERROR.format(status=status))
    return STATUS_HAS_CHANGED.format(
        homework_name=homework["homework_name"],
        verdict=HOMEWORK_VERDICTS[status]
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)

    timestamp = int(time.time())
    previous_verdict = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)['homeworks']
            if not homeworks:
                continue
            verdict = parse_status(homeworks[0])
            if previous_verdict != verdict:
                previous_verdict = verdict
                if send_message(bot, verdict):
                    timestamp = response.get('current_date', timestamp)
            else:
                logging.debug(STATUS_HAS_NOT_CHANGED)
        except Exception as error:
            logging.exception(EXCEPTION_ERROR.format(error=error))
            send_message(bot, EXCEPTION_BOT_ERROR.format(error=error))
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=('%(asctime)s, '
                '%(levelname)s, '
                '%(funcName)s, '
                '%(lineno)d, '
                '%(message)s'
                ),
        handlers=[logging.FileHandler(__file__ + '.log'),
                  logging.StreamHandler(sys.stdout)]
    )

    main()
