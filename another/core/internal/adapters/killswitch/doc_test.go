package killswitch

import "testing"

func TestLinuxNFTScriptContainsInterfaceAndPermit(t *testing.T) {
	// Компилируется на всех ОС: проверяем генератор через неэкспортированную
	// копию логики нельзя. Этот тест — заглушка-документация; реальный
	// рендер проверяется в linux_nft_test.go под linux.
	t.Log("nft renderer tested on linux build tag")
}
