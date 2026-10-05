### Topics your draft should cover

1. **Login methods (one user, many providers).** A typical shape is `user_identities(user_id, provider, provider_user_id)`, unique on `(provider, provider_user_id)`. Decide which providers the MVP needs: email + password only, or GitHub/Google too?
2. **Passwords.** Store only a hash (argon2 or bcrypt), never the password itself. Where does the hash live: a column in the identity row (only for `provider = 'password'`), or a separate `password_credentials` table? This is a good normalization question for the course.
3. **Admin flag.** You want it apart from `users`. What table holds it? If there's no per-user auth table, a small `admins(user_id)` table also works: being in the table means being an admin. Compare that with a boolean column.
4. **Sessions.** You can keep them in the DB (a `sessions` table) or use a JWT (a signed token that the server doesn't store). I recommend the DB here: you can log someone out, and you can show the course a real table. Store a hash of the token, not the token itself. Add `expires_at` and `revoked_at`.
5. **One-time tokens.** Email confirmation and password reset each need one. Is that MVP or backlog? If MVP, think about one table with a `purpose` enum versus two tables.
6. **Linking accounts.** Someone logs in with Google using an email that already exists. Do we link that login to the existing account automatically? This is a known way to take over an account if the provider doesn't verify emails. Decide on a rule.
7. **Workspace invites.** Group 1 has `memberships`, but nothing for an invite someone hasn't accepted yet. Does auth or Group 1 own `invitations`? It might be a missing table.
8. **Secret store** (parked earlier). API keys for model providers: are they global (admin) or per user? If they're stored in Postgres, they must be encrypted, with the encryption key outside the DB (in an env variable).
9. **Delete rules.** Deleting a user should also delete their identities and sessions (`CASCADE`). `activity_events` keeps the copied names.
10. **What to log.** Logins and failed logins should go to system logs, not to `activity_events`. Admin actions go to `activity_events`, as we decided.

# Способы входа

Используй стандартную схему, даже не смотря на то что пока что мы остановимся только на связке email + password, никто не зарпещает позже нам захотеть добавить автризацию через гит и гугл. Так что стандартный подход для работы с несколькими провайдерами, отдельно таблица для нашего учета email + password авторизаций. Было бы неплохо добавить в последнюю поле email_verified, хоть мы и не будем пока под него код пистаь

# Пароли

Думаю хочется табличку с credentials, выбери как лучше это стакнуть с нашим учетом email + pass

# Админ

Отдельная таблица, которая содержит записи (user_id, granted_at, и кто выдал), есть id в таблице - ты админ, поле того кто выдал пока просто текстом сделать на первое время без ключиков

# Сессии

Делаем сессии с access + refresh токеном, используем БД

# Одноразовые токены

Пока предлагаю в целом отказаться от сценариев где они используются

# Линк аккаунтов

Оно будет конечно, но не сейчас. Пока в долгий ящик, у нас один провайдер

# Инвайты

Пока предлагаю сойтись на том что мы все-таки не инвайтим, а именно добавляем людей, чтобы особо не возиться с этим всем

# Secret store

Все еще остается на подумать, доступен он только администраторам и нашей системе, скорее всего это не postgres будет

# Delete rules

Да, просто каскад с отображением вроде "Удален пользователь User228 с данными email, google"

# Логи

Я честно пока считаю что нам нет необходимости трекать и эту информацию тоже полноценно, кроме назначения и удаления админов