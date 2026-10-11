include $(TOPDIR)/rules.mk

PKG_NAME:=easytether-usb-tiny
PKG_VERSION:=0.8.9
PKG_RELEASE:=5
PKG_LICENSE:=Proprietary
PKG_MAINTAINER:=easytether-openwrt <support@mobile-stream.com>

include $(INCLUDE_DIR)/package.mk

define Package/easytether-usb-tiny
  SECTION:=net
  CATEGORY:=Network
  TITLE:=EasyTether USB tethering (router-side, prebuilt)
  DEPENDS:=+kmod-tun
  URL:=http://www.mobile-stream.com/easytether/drivers.html
endef

define Package/easytether-usb-tiny/description
  Router-side component of EasyTether by Mobile Stream.
  Prebuilt binary for mipsel_24kc (Xiaomi Mi Router 3G / R3G).
  Enables Internet connection sharing from an Android phone running
  the EasyTether app over USB (tap-easytether interface).
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Compile
	true
endef

define Package/easytether-usb-tiny/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/usr/bin/easytether-usb $(1)/usr/bin/
	$(INSTALL_DIR) $(1)/etc/easytether
	$(INSTALL_DATA) ./files/etc/easytether/adbkey.README $(1)/etc/easytether/
	$(INSTALL_DIR) $(1)/etc/hotplug.d/usb
	$(INSTALL_BIN) ./files/etc/hotplug.d/usb/99-easytether-usb $(1)/etc/hotplug.d/usb/
	$(INSTALL_DIR) $(1)/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/lib/upgrade/keep.d/easytether-usb-tiny $(1)/lib/upgrade/keep.d/
endef

$(eval $(call BuildPackage,easytether-usb-tiny))
