plugins {
    id("com.android.application")
    kotlin("android")
}

android {
    namespace = "dev.gitgui"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.gitgui"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    signingConfigs {
        create("release") {
            val keystore = System.getenv("GITGUI_KEYSTORE") ?: project.findProperty("gitgui.keystore") as String?
            if (keystore != null) {
                storeFile = file(keystore)
                storePassword = System.getenv("GITGUI_KEYSTORE_PASSWORD") ?: project.findProperty("gitgui.storePassword") as String?
                keyAlias = System.getenv("GITGUI_KEY_ALIAS") ?: project.findProperty("gitgui.keyAlias") as String?
                keyPassword = System.getenv("GITGUI_KEY_PASSWORD") ?: project.findProperty("gitgui.keyPassword") as String?
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            val ks = signingConfigs.getByName("release")
            if (ks.storeFile != null) signingConfig = ks
        }
        debug {
            applicationIdSuffix = ".debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}
