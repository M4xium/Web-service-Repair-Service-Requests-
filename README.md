# Веб-сервис «Заявки в ремонтную службу»

Приложение для приёма и обработки заявок с ролями **диспетчер** и **мастер**.

## Реализовано

- Страница создания заявки (`new` по умолчанию).
- Панель диспетчера: список, фильтр по статусу, назначение мастера (`assigned`), отмена (`canceled`).
- Панель мастера: список своих заявок, «Взять в работу» (`assigned -> in_progress`), «Завершить» (`in_progress -> done`).
- Защита от гонки на «Взять в работу»: атомарный SQL `UPDATE ... WHERE status='assigned'`.

## Запуск (Docker Compose)

```bash
docker compose up --build
```

Приложение: http://localhost:3000

## Запуск без Docker

```bash
python -m app.server
```

## Тестовые пользователи (сиды)

- `dispatcher_anna` — диспетчер
- `master_ivan` — мастер
- `master_olga` — мастер

Вход на главной через выбор пользователя.

## Проверка гонки

### Скриптом

```bash
./race_test.sh 2
```

Ожидаемо: один ответ `200`, второй `409`.

### Два терминала вручную

```bash
curl -i -X POST -H "Accept: application/json" -H "Cookie: userId=2" http://localhost:3000/master/requests/2/take
```

Одновременно запустить в двух терминалах; должен быть один `200` и один `409`.

## Автотесты

```bash
python -m unittest discover -s tests -v
```
