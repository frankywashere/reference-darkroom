// Reference Darkroom's adapter. Nikon's licensed headers/binaries remain local.
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#include <CoreFoundation/CoreFoundation.h>
#include <Carbon/Carbon.h>
#include "Maid3.h"
#include "Maid3d1.h"
#include <atomic>
#include <chrono>
#include <iostream>
#include <mutex>
#include <thread>
#include <unistd.h>

static FILE *wire;
static std::mutex outputLock, frameLock;
static std::atomic<bool> running{true}, connected{false}, live{false};
static NSString *frameFile;
static std::string destination;
static NkMAIDCSCallback callbacks{};
static LPMAIDInitializeSDKProc initializeSDK;
static LPMAIDFreeSDKProc freeSDK;
static LPMAIDEnumDevices enumDevices;
static LPMAIDConnectDeviceProc connectDevice;
static LPMAIDDisconnectDeviceProc disconnectDevice;
static LPMAIDStartLiveView startLive;
static LPMAIDStopLiveView stopLive;
static LPMAIDGetLiveViewStatus liveStatus;
static LPMAIDStartShooting shoot;
static LPMAIDGetCapability getCap;
static LPMAIDSetCapability setCap;
static LPMAIDSetImageVideoSavePath savePaths;
static ULONG previousSaveMedia=0;
static bool restoreSaveMedia=false;
static NkMAIDEnum previousRaw{};
static bool restoreRaw=false;
static MAIDShootingStructure shootingParams{};
static std::atomic<bool> shooting{false};

static NKERROR restoreDestination(){NKERROR error=0;if(restoreRaw){NKERROR rc=setCap(kNkMAIDCapability_CompressRAWEx,&previousRaw,kNkMAIDDataType_EnumPtr);fprintf(stderr,"Restore RAW index %u: SDK %d\n",previousRaw.ulValue,rc);if(rc)error=rc;restoreRaw=false;}if(restoreSaveMedia){NKERROR rc=setCap(kNkMAIDCapability_SaveMedia,&previousSaveMedia,kNkMAIDDataType_UnsignedPtr);fprintf(stderr,"Restore save media %u: SDK %d\n",previousSaveMedia,rc);if(rc&&!error)error=rc;restoreSaveMedia=false;}return error;}

static void send(NSDictionary *message){@autoreleasepool{
    NSData *data=[NSJSONSerialization dataWithJSONObject:message options:0 error:nil];
    if(!data)return;std::lock_guard<std::mutex> lock(outputLock);
    fwrite(data.bytes,1,data.length,wire);fputc('\n',wire);fflush(wire);
}}
static NSString *text(const char *s){return s?([NSString stringWithUTF8String:s]?:@""):@"";}
static void event(NKREF,ULONG code,NKPARAM data){@autoreleasepool{
    if(code==kNkMAIDEvent_ImageSaved){send(@{@"event":@"capture_saved",@"path":text((char*)data)});free((void*)data);}
    else if(code==kNkMAIDEvent_CapChange||code==kNkMAIDEvent_CapChangeOperationOnly){free((void*)data);send(@{@"event":@"settings_changed"});}
    else if(code==kNkMAIDEvent_DeviceInfoChanged){send(@{@"event":@"devices_changed"});}
    else if(code==kNkMAIDEvent_CaptureComplete){shooting=false;send(@{@"event":@"capture_complete"});}
    else if(code==kNkMAIDEvent_StorageFull_ImageNotSaved||code==kNkMAIDEvent_AcquireFailed_ImageNotSaved){send(@{@"event":@"error",@"message":@"Camera could not save the capture.",@"sdk_code":@(code)});}
    else if(code==kNkMAIDEvent_LiveViewStateChanged){send(@{@"event":@"live_changed"});}
}}
static ULONG uiRequest(NKREF,LPNkMAIDUIRequestInfo info){
    send(@{@"event":@"error",@"message":text((char*)info->lpPrompt)});
    return kNkMAIDUIRequestResult_Cancel;
}
static void progress(ULONG,ULONG,NKREF,ULONG done,ULONG total){
    // Only report coarse progress; frames/callbacks must not backlog the UI.
    if(done==0||done>=total)send(@{@"event":@"transfer",@"done":@(done),@"total":@(total)});
}
static NKERROR dataProc(NKREF,LPVOID,LPVOID){return kNkMAIDResult_NoError;}
static NKERROR liveFrame(NKREF,LPNkMAIDLiveViewData frame){@autoreleasepool{
    if(frame){
        std::lock_guard<std::mutex> lock(frameLock);
        static auto last=std::chrono::steady_clock::time_point{};
        auto now=std::chrono::steady_clock::now();
        if(frame->pImageData&&frame->ulLvImageSize&&frame->ulLvImageSize<32*1024*1024&&now-last>=std::chrono::milliseconds(80)){
            NSData *jpg=[NSData dataWithBytes:frame->pImageData length:frame->ulLvImageSize];
            if([jpg writeToFile:frameFile options:NSDataWritingAtomic error:nil]){last=now;live=true;}
        }
        free(frame->pImageData);free(frame);
    }
    return kNkMAIDResult_NoError;
}}
static void completion(NKREF,NKERROR code){shooting=false;send(@{@"event":@"shooting_result",@"sdk_code":@(code)});}
static void releaseCaps(LPNkMAIDEnumCapInfo caps){if(caps){free(caps->pCapArray);free(caps);}}
static NSDictionary *devices(){
    LPNkMAIDEnumDevices list=nullptr;NKERROR code=enumDevices(list,nullptr,nullptr);
    NSMutableArray *items=[NSMutableArray array];
    if(code==0&&list&&list->pDeviceData)for(ULONG i=0;i<list->ulElements;i++){
        auto &d=list->pDeviceData[i];[items addObject:@{@"id":@(d.ID),@"name":text(d.Name),@"available":@(d.Availability),@"firmware":text(d.Version)}];
    }
    if(list){free(list->pDeviceData);free(list);}
    return @{@"sdk_code":@(code),@"devices":items};
}
static void freeValue(LPVOID p,eNkMAIDDataType type){if(!p)return;if(type==kNkMAIDDataType_EnumPtr)free(((LPNkMAIDEnum)p)->pData);else if(type==kNkMAIDDataType_ArrayPtr)free(((LPNkMAIDArray)p)->pData);free(p);}
static const std::pair<const char*,ULONG> exposureCaps[]={
    {"iso",kNkMAIDCapability_Sensitivity},{"shutter",kNkMAIDCapability_ShutterSpeed},{"aperture",kNkMAIDCapability_Aperture},{"mode",kNkMAIDCapability_ExposureMode}};
static ULONG capability(NSString *key){for(auto item:exposureCaps)if([key isEqualToString:text(item.first)])return item.second;return 0;}
static NSDictionary *settings(){
    NSMutableDictionary *result=[NSMutableDictionary dictionary];
    for(auto item:exposureCaps){
        LPVOID p=nullptr;eNkMAIDDataType type=kNkMAIDDataType_Null;
        NKERROR code=getCap(item.second,kNkSDKGetSettingValue,p,type);
        if(code==0&&p&&type==kNkMAIDDataType_EnumPtr){
            auto value=*((LPNkMAIDEnum)p);freeValue(p,type);p=nullptr;
            code=getCap(item.second,kNkSDKGetSettingSupportedValueArray,p,type);
            NSMutableArray *options=[NSMutableArray array];
            if(code==0&&p&&type==kNkMAIDDataType_EnumPtr){
                auto a=(LPNkMAIDEnum)p;
                // Use camera-provided strings, avoiding guesses about numeric encodings.
                if(a->ulType==kNkMAIDArrayType_PackedString&&a->pData&&a->wPhysicalBytes>0){
                    const char *s=(char*)a->pData,*end=s+a->ulElements*a->wPhysicalBytes;
                    for(ULONG i=0;i<1024&&s<end;i++){size_t len=strnlen(s,end-s);if(s+len>=end)break;[options addObject:@{@"index":@(i),@"label":text(s)}];s+=len+1;}
                }else if(item.second==kNkMAIDCapability_ExposureMode&&a->ulType==kNkMAIDArrayType_Unsigned&&a->wPhysicalBytes>0&&a->wPhysicalBytes<=8&&a->pData){
                    for(ULONG i=0;i<a->ulElements&&i<64;i++){ULONG mode=0;memcpy(&mode,(char*)a->pData+i*a->wPhysicalBytes,std::min(4,(int)a->wPhysicalBytes));NSString *label=nil;
                        switch(mode){case kNkMAIDExposureMode_Program:label=@"P · Program";break;case kNkMAIDExposureMode_AperturePriority:label=@"A · Aperture priority";break;case kNkMAIDExposureMode_SpeedPriority:label=@"S · Shutter priority";break;case kNkMAIDExposureMode_Manual:label=@"M · Manual";break;default:break;}
                        if(label)[options addObject:@{@"index":@(i),@"label":label}];
                    }
                }
            }
            [result setObject:@{@"index":@(value.ulValue),@"options":options,@"type":@(value.ulType),@"elements":@(value.ulElements)} forKey:text(item.first)];
        }else if(code==0&&p&&type==kNkMAIDDataType_UnsignedPtr){
            [result setObject:@{@"value":@(*((ULONG*)p)),@"options":@[]} forKey:text(item.first)];
        }
        freeValue(p,type);
    }
    return result;
}
static NSDictionary *command(NSDictionary *request){
    NSString *op=request[@"op"];NKERROR code=0;NSDictionary *extra=@{};
    if([op isEqualToString:@"devices"])return devices();
    if([op isEqualToString:@"connect"]){
        if(connected)return @{@"sdk_code":@(-1),@"message":@"A camera is already connected."};
        NSString *folder=request[@"destination"];if(![folder isKindOfClass:NSString.class]||folder.length==0||[folder lengthOfBytesUsingEncoding:NSUTF8StringEncoding]>=255)return @{@"sdk_code":@(-1),@"message":@"Capture folder path must be shorter than 255 UTF-8 bytes."};
        LPNkMAIDEnumCapInfo caps=nullptr;code=connectDevice([request[@"device_id"] unsignedIntValue],&caps);releaseCaps(caps);
        if(code==0){connected=true;destination=folder.UTF8String;if(destination.back()!='/')destination+='/';NkMAIDString path{};strncpy((char*)path.str,destination.c_str(),sizeof(path.str)-1);
            code=savePaths(destination.c_str(),destination.c_str());
            if(code==0){LPVOID p=nullptr;eNkMAIDDataType type=kNkMAIDDataType_Null;code=getCap(kNkMAIDCapability_SaveMedia,kNkSDKGetSettingValue,p,type);
                if(code==0&&p&&type==kNkMAIDDataType_UnsignedPtr){previousSaveMedia=*((ULONG*)p);restoreSaveMedia=true;ULONG both=kNkMAIDSaveMedia_Card_SDRAM;code=setCap(kNkMAIDCapability_SaveMedia,&both,kNkMAIDDataType_UnsignedPtr);}else if(code==0)code=-1;
                freeValue(p,type);
            }
            if(code==0&&[request[@"lossless"] boolValue]){
                LPVOID p=nullptr;eNkMAIDDataType type=kNkMAIDDataType_Null;code=getCap(kNkMAIDCapability_CompressRAWEx,kNkSDKGetSettingValue,p,type);
                if(code==0&&p&&type==kNkMAIDDataType_EnumPtr){previousRaw=*((LPNkMAIDEnum)p);previousRaw.pData=nullptr;restoreRaw=true;}else if(code==0)code=-1;
                freeValue(p,type);
                if(code==0){p=nullptr;code=getCap(kNkMAIDCapability_CompressRAWEx,kNkSDKGetSettingSupportedValueArray,p,type);ULONG index=UINT32_MAX;
                    if(code==0&&p&&type==kNkMAIDDataType_EnumPtr){auto a=(LPNkMAIDEnum)p;if(a->pData&&a->ulType==kNkMAIDArrayType_Unsigned&&a->wPhysicalBytes>0&&a->wPhysicalBytes<=4)for(ULONG i=0;i<a->ulElements;i++){ULONG value=0;memcpy(&value,(char*)a->pData+i*a->wPhysicalBytes,a->wPhysicalBytes);if(value==kNkMAIDCompressRAWEx_LosslessCompressed){index=i;break;}}}
                    freeValue(p,type);if(code==0){if(index==UINT32_MAX)code=-1;else{NkMAIDEnum v=previousRaw;v.ulValue=index;code=setCap(kNkMAIDCapability_CompressRAWEx,&v,kNkMAIDDataType_EnumPtr);}}
                }
            }
            if(code!=0){restoreDestination();disconnectDevice();connected=false;}else extra=@{@"settings":settings()};
        }
    }else if([op isEqualToString:@"disconnect"]){if(connected){if(live)stopLive(nullptr,nullptr);NKERROR restored=restoreDestination();code=disconnectDevice();if(code==0){live=false;connected=false;destination.clear();if(restored)return @{@"sdk_code":@(restored),@"message":@"Disconnected, but camera settings could not be restored. Check RAW compression and save destination on the camera."};}}}
    else if(!connected)return @{@"sdk_code":@(-1),@"message":@"Connect a camera first."};
    else if([op isEqualToString:@"live_start"]){code=startLive(nullptr,nullptr);if(code==0||code==kNkMAIDAPIResult_LiveViewAlreadyStarted){live=true;code=0;}}
    else if([op isEqualToString:@"live_stop"]){code=stopLive(nullptr,nullptr);if(code==0||code==kNkMAIDAPIResult_LiveViewAlreadyStopped){live=false;code=0;}}
    else if([op isEqualToString:@"status"]){eNkMAIDLVStatus status=eNkMAIDLVStatus_OFF;code=liveStatus(status);if(code==0)live=status!=eNkMAIDLVStatus_OFF;}
    else if([op isEqualToString:@"capture"]){
        if(shooting)return @{@"sdk_code":@(-1),@"message":@"A capture is still in progress."};
        shootingParams={};auto &params=shootingParams;params.ShootingType=kNkSDKShootingTypeSingle;params.bAutoFocus=[request[@"autofocus"] boolValue];
        // Nikon rejects Single when the body's release selector is continuous.
        // Request exactly one frame without changing the body's release setting.
        LPVOID p=nullptr;eNkMAIDDataType type=kNkMAIDDataType_Null;NKERROR rc=getCap(kNkMAIDCapability_ShootingMode,kNkSDKGetSettingValue,p,type);
        if(rc==0&&p&&type==kNkMAIDDataType_EnumPtr){auto v=(LPNkMAIDEnum)p;ULONG mode=v->ulValue;
            if(v->pData&&v->ulType==kNkMAIDArrayType_Unsigned&&v->wPhysicalBytes>0&&v->wPhysicalBytes<=4&&v->ulValue<v->ulElements){mode=0;memcpy(&mode,(char*)v->pData+v->ulValue*v->wPhysicalBytes,v->wPhysicalBytes);}
            if(mode==eNkMAIDShootingMode_C||mode==eNkMAIDShootingMode_CH){params.ShootingType=kNkSDKShootingTypeContinuous;params.ulContinuous_Interval_NumShots=1;}
            else if(mode==eNkMAIDShootingMode_SelfTimer){params.ShootingType=kNkSDKShootingTypeSelfTimer;params.ulContinuous_Interval_NumShots=1;}
        }freeValue(p,type);
        strncpy(params.ImageSavePath,destination.c_str(),sizeof(params.ImageSavePath)-1);shooting=true;code=shoot(params,completion,nullptr);
        if(code==kNkMAIDResult_Pending)code=0;
        if(code!=0)shooting=false;
    }
    else if([op isEqualToString:@"settings"])extra=@{@"settings":settings()};
    else if([op isEqualToString:@"session_settings"]){NSMutableDictionary *values=[NSMutableDictionary dictionary];for(ULONG cap:{(ULONG)kNkMAIDCapability_CompressRAWEx,(ULONG)kNkMAIDCapability_SaveMedia}){LPVOID p=nullptr;eNkMAIDDataType type=kNkMAIDDataType_Null;NKERROR rc=getCap(cap,kNkSDKGetSettingValue,p,type);if(rc==0&&p){if(type==kNkMAIDDataType_EnumPtr)values[cap==kNkMAIDCapability_SaveMedia?@"save_media":@"raw_index"]=@(((LPNkMAIDEnum)p)->ulValue);else if(type==kNkMAIDDataType_UnsignedPtr)values[@"save_media"]=@(*((ULONG*)p));}freeValue(p,type);}extra=@{@"session_settings":values};}
    else if([op isEqualToString:@"setting"]){
        ULONG cap=capability(request[@"key"]);if(!cap)return @{@"sdk_code":@(-1),@"message":@"Unsupported camera setting."};
        LPVOID p=nullptr;eNkMAIDDataType type=kNkMAIDDataType_Null;code=getCap(cap,kNkSDKGetSettingValue,p,type);
        if(code==0&&p&&type==kNkMAIDDataType_EnumPtr){NkMAIDEnum v=*((LPNkMAIDEnum)p);freeValue(p,type);p=nullptr;v.pData=nullptr;v.ulValue=[request[@"index"] unsignedIntValue];if(v.ulValue>=v.ulElements)code=-1;else code=setCap(cap,&v,kNkMAIDDataType_EnumPtr);}else if(code==0)code=-1;
        freeValue(p,type);if(code==0)extra=@{@"settings":settings()};
    }else code=-1;
    NSMutableDictionary *response=[extra mutableCopy];response[@"sdk_code"]=@(code);response[@"connected"]=@(connected.load());response[@"live"]=@(live.load());return response;
}
int main(int argc,char **argv){@autoreleasepool{
    if(argc!=3)return 2;frameFile=text(argv[2]);
    wire=fdopen(dup(STDOUT_FILENO),"w");dup2(STDERR_FILENO,STDOUT_FILENO);
    [NSApplication sharedApplication];
    NSURL *url=[NSURL fileURLWithPath:text(argv[1])];CFBundleRef bundle=CFBundleCreate(kCFAllocatorDefault,(__bridge CFURLRef)url);
    if(!bundle||!CFBundleLoadExecutable(bundle)){send(@{@"event":@"fatal",@"message":@"Unable to load Nikon SDK module."});return 3;}
    auto symbol=[&](NSString *name){return CFBundleGetFunctionPointerForName(bundle,(__bridge CFStringRef)name);};
    initializeSDK=(LPMAIDInitializeSDKProc)symbol(@"InitializeSDK");freeSDK=(LPMAIDFreeSDKProc)symbol(@"FreeSDK");enumDevices=(LPMAIDEnumDevices)symbol(@"EnumDevices");connectDevice=(LPMAIDConnectDeviceProc)symbol(@"ConnectDevice");disconnectDevice=(LPMAIDDisconnectDeviceProc)symbol(@"DisconnectDevice");startLive=(LPMAIDStartLiveView)symbol(@"StartLiveView");stopLive=(LPMAIDStopLiveView)symbol(@"StopLiveView");liveStatus=(LPMAIDGetLiveViewStatus)symbol(@"GetLiveViewStatus");shoot=(LPMAIDStartShooting)symbol(@"StartShooting");getCap=(LPMAIDGetCapability)symbol(@"GetCapability");setCap=(LPMAIDSetCapability)symbol(@"SetCapability");
    savePaths=(LPMAIDSetImageVideoSavePath)symbol(@"SetImageVideoSavePath");
    if(!initializeSDK||!freeSDK||!enumDevices||!connectDevice||!disconnectDevice||!startLive||!stopLive||!liveStatus||!shoot||!getCap||!setCap||!savePaths){send(@{@"event":@"fatal",@"message":@"Nikon SDK exports do not match version 2."});return 4;}
    callbacks.pUIReqProc=(LPNKFUNC)uiRequest;callbacks.pfnEventProc=(LPNKFUNC)event;callbacks.pProgressProc=(LPNKFUNC)progress;callbacks.pDataProc=(LPNKFUNC)dataProc;callbacks.pLiveViewDataProc=(LPNKFUNC)liveFrame;
    std::thread worker([]{@autoreleasepool{
        NKERROR code=initializeSDK(malloc,free,&callbacks,nullptr,nullptr);
        if(code!=0){send(@{@"event":@"fatal",@"message":@"Nikon SDK initialization failed.",@"sdk_code":@(code)});running=false;return;}
        send(@{@"event":@"ready",@"sdk_version":@"2.0.0"});
        std::string line;while(std::getline(std::cin,line)){@autoreleasepool{
            NSData *data=[NSData dataWithBytes:line.data() length:line.size()];id request=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if(![request isKindOfClass:NSDictionary.class])continue;
            NSMutableDictionary *response=[command(request) mutableCopy];response[@"id"]=request[@"id"]?:@"";send(response);
        }}
        if(connected){if(live)stopLive(nullptr,nullptr);restoreDestination();disconnectDevice();}freeSDK();running=false;
    }});
    while(running){@autoreleasepool{CFRunLoopRunInMode(kCFRunLoopDefaultMode,.02,false);}}
    worker.join();CFRelease(bundle);return 0;
}}
