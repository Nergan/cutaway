package tun

import "os"

// filePacket — PacketDevice поверх fd TUN (Linux/Android, IFF_NO_PI).
type filePacket struct {
	f    *os.File
	name string
}

func (f *filePacket) ReadPacket(buf []byte) (int, error) {
	return f.f.Read(buf)
}

func (f *filePacket) WritePacket(pkt []byte) error {
	_, err := f.f.Write(pkt)
	return err
}

func (f *filePacket) Close() error { return f.f.Close() }

func (f *filePacket) Name() string { return f.name }
