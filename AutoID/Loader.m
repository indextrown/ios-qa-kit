//
//  Loader.m
//  QAAutoID
//
//  dylib가 앱에 주입되면 +load가 자동 실행되어 QAAutoID를 시작한다.
//

#import <Foundation/Foundation.h>

@interface QAAutoIDLoader : NSObject
@end

@implementation QAAutoIDLoader

+ (void)load {
    Class cls = NSClassFromString(@"QAAutoID");
    SEL start = NSSelectorFromString(@"start");
    if (cls && [cls respondsToSelector:start]) {
        ((void (*)(id, SEL))[cls methodForSelector:start])(cls, start);
    } else {
        NSLog(@"[QAAutoID] loader: QAAutoID class not found");
    }
}

@end
