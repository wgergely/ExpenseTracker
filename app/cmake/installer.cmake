cmake_minimum_required(VERSION 3.31)

# ───────────────────────────────────────────────────────────
# CPACK WIX installer settings
# ───────────────────────────────────────────────────────────

set(CPACK_PACKAGE_NAME              "${PROJECT_NAME}")
set(CPACK_PACKAGE_VENDOR            "${PROJECT_NAME}")
set(CPACK_PACKAGE_DESCRIPTION       "${PROJECT_NAME}: personal expense tracker that connects with a google sheet")
set(CPACK_PACKAGE_VERSION           "${PROJECT_VERSION}")
set(CPACK_PACKAGE_VERSION_MAJOR     "${PROJECT_VERSION_MAJOR}")
set(CPACK_PACKAGE_VERSION_MINOR     "${PROJECT_VERSION_MINOR}")
set(CPACK_PACKAGE_VERSION_PATCH     "${PROJECT_VERSION_PATCH}")
set(CPACK_PACKAGE_CONTACT           "hello+${PROJECT_NAME}@gergely-wootch.com")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "Programs/${PROJECT_NAME}")
set(CPACK_PACKAGE_EXECUTABLES       "ExpenseTracker.exe" "${PROJECT_NAME}")
set(CPACK_WIX_PROGRAM_MENU_FOLDER   "${PROJECT_NAME}")

set(CPACK_WIX_VERSION             4)

set(CPACK_WIX_INSTALL_SCOPE      "perUser")
set(CPACK_WIX_ROOT_FOLDER_ID     "LocalAppDataFolder")

set(CPACK_WIX_BUILD_EXTENSIONS   "WixToolset.UI.wixext"
                                 "WixToolset.Util.wixext")  

# WiX GUIDs
#   - UPGRADE_GUID is your stable UpgradeCode → enables proper major upgrades
#   - PRODUCT_GUID  is your Product/@Id → must be unique per MSI
set(CPACK_WIX_UPGRADE_GUID       "19f3fc80-e2fa-4551-a0a2-b1f109135aa4" CACHE STRING "")
set(CPACK_WIX_PRODUCT_GUID       "8b00aeca-0945-4a2a-afbd-73079d5b6af5" CACHE STRING "")

#  License & icon
set(CPACK_RESOURCE_FILE_LICENSE  "${CMAKE_SOURCE_DIR}/installer/gpl-3.0.rtf") 
set(CPACK_WIX_PRODUCT_ICON       "${CMAKE_SOURCE_DIR}/rsc/icon.ico")

# UI & branding bitmaps
set(CPACK_WIX_UI_REF             "WixUI_InstallDir")                                # <UIRef Id=…/>
set(CPACK_WIX_UI_BANNER          "${CMAKE_SOURCE_DIR}/installer/banner.bmp")        # 493×58
set(CPACK_WIX_UI_DIALOG          "${CMAKE_SOURCE_DIR}/installer/background.bmp")    # 493×312

# Start‐menu folder
set(CPACK_WIX_PROGRAM_MENU_FOLDER "${PROJECT_NAME}")

# Localization
#    semicolon- or comma-delimited list of culture codes
set(CPACK_WIX_CULTURES           "en-US")

# “Add/Remove Programs” custom properties
set(CPACK_WIX_PROPERTY_ARPCOMMENTS      "${PROJECT_NAME} installer")
set(CPACK_WIX_PROPERTY_ARPHELPLINK      "https://github.com/wgergely/ExpenseTracker")
set(CPACK_WIX_PROPERTY_ARPURLINFOABOUT  "https://github.com/wgergely/ExpenseTracker")
set(CPACK_WIX_PROPERTY_ARPURLUPDATEINFO "https://github.com/wgergely/ExpenseTracker")

# Root‐feature metadata
set(CPACK_WIX_ROOT_FEATURE_TITLE       "${PROJECT_NAME}")
set(CPACK_WIX_ROOT_FEATURE_DESCRIPTION "Installs ${PROJECT_NAME}")

# Add the {InstallDir}/lib and packages directories to the installer
set(CPACK_INSTALLED_DIRECTORIES 
    "${CMAKE_INSTALL_PREFIX}/lib" "lib"
    "${CMAKE_INSTALL_PREFIX}/packages" "packages"
)

# Pick WiX as your generator and activate CPack
set(CPACK_GENERATOR "ZIP;WIX")
set(CPACK_CONFIGURATION_TYPES "Release")
include(CPack)