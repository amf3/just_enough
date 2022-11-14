package main

import (
	"buildit/rootfs"
	"fmt"
)

func main() {
	fmt.Println("Hello, Modules!")
	rootfs.MakeTopLevelDirectories()
}
