package domain

// SessionCredentials — то, что control-plane выдаёт после успешного
// challenge-response (§7.2 спецификации). Два разных значения:
//   - BearerToken — короткоживущий токен, которым транспорт может
//     дополнительно подтверждаться перед узлом (напр. заголовок Authorization
//     при апгрейде WebSocket), если узел это проверяет.
//   - VLESSUserID — UUID, вшиваемый в заголовок VLESS-запроса
//     (см. vlessproto.EncodeRequestHeader). Это отдельный "билет" на
//     data-plane, который control-plane выпускает вместе с BearerToken —
//     не путать с Ed25519-идентичностью устройства, которая используется
//     только для самого challenge-response, а не для VLESS.
type SessionCredentials struct {
	BearerToken string
	VLESSUserID [16]byte
}
