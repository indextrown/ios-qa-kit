// 실행기 본체는 androidTest 쪽(instrumentation)에 있다. 앱 쪽은 빈 껍데기.
plugins {
    id("com.android.application")
}

android {
    namespace = "com.qakit.runner"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.qakit.runner"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test:core:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
}
