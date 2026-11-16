// qakit 안드로이드 상주 실행기 (UiAutomator2 instrumentation). qakit이 처음 쓸 때 빌드한다.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "qakit-android-runner"
include(":runner")
