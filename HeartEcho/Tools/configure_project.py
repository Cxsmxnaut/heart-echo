#!/usr/bin/env python3
"""Recreate the standalone Heart Echo project, without touching ChestBPM."""
import hashlib, json
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
objects={}
def key(name): return hashlib.sha256(('HeartEcho:'+name).encode()).hexdigest()[:24].upper()
def obj(label,isa,**values):
    ident=key(label); objects[ident]={'isa':isa,**values}; return ident
def file(path,kind='sourcecode.swift',**extra): return obj('file:'+path,'PBXFileReference',path=path,sourceTree='SOURCE_ROOT',lastKnownFileType=kind,**extra)
def build(ref,target): return obj('build:'+target+ref,'PBXBuildFile',fileRef=ref)
def phase(label,isa,files,**extra): return obj(label,isa,buildActionMask='2147483647',files=files,runOnlyForDeploymentPostprocessing='0',**extra)
def configs(name,common,debug=None,release=None):
    refs=[]
    for config,extra in [('Debug',debug or {}),('Release',release or {})]:
        refs.append(obj(name+config,'XCBuildConfiguration',name=config,buildSettings={**common,**extra}))
    return obj(name+'configs','XCConfigurationList',buildConfigurations=refs,defaultConfigurationIsVisible='0',defaultConfigurationName='Release')
project='000000000000000000000001';main='000000000000000000000005'
ui=[file(str(p.relative_to(ROOT))) for p in sorted((ROOT/'HeartEchoApp').glob('*.swift'))]
engine=[file(str(p.relative_to(ROOT))) for p in sorted((ROOT/'Engine').glob('*.swift'))]
shared=[file('Engine/'+x) for x in ['WatchLink.swift','TrialProtocol.swift','DiagnosticLog.swift']]
watchsrc=file('Watch/HeartEchoWatch.swift');tests=[file(str(p.relative_to(ROOT))) for p in sorted((ROOT/'UITests').glob('*.swift'))]
models=[file('Models/'+n+'.mlpackage','folder.mlpackage') for n in ['BeatStates','Murmur']]
samples=file('Resources/MurmurSamples','folder')
assets=file('HeartEchoApp/Assets.xcassets','folder.assetcatalog')
products=[obj('product:'+name,'PBXFileReference',path=name,sourceTree='BUILT_PRODUCTS_DIR',explicitFileType=kind) for name,kind in [('HeartEchoApp.app','wrapper.application'),('HeartEchoWatch.app','wrapper.application'),('HeartEchoUITests.xctest','wrapper.cfbundle')]]
watch=key('watchtarget');test=key('testtarget')
proxy=obj('watchproxy','PBXContainerItemProxy',containerPortal=project,proxyType='1',remoteGlobalIDString=watch,remoteInfo='HeartEchoWatch')
dependency=obj('watchdependency','PBXTargetDependency',target=watch,targetProxy=proxy)
watchbuild=build(products[1],'embed');objects[watchbuild]['settings']={'ATTRIBUTES':['RemoveHeadersOnCopy']}
embed=phase('embed','PBXCopyFilesBuildPhase',[watchbuild],dstPath='$(CONTENTS_FOLDER_PATH)/Watch',dstSubfolderSpec='16',name='Embed Watch App')
base={'CODE_SIGN_STYLE':'Automatic','DEVELOPMENT_TEAM':'6L2L492NHQ','GENERATE_INFOPLIST_FILE':'YES','PRODUCT_NAME':'$(TARGET_NAME)','SWIFT_VERSION':'5.0'}
app={**base,'ASSETCATALOG_COMPILER_APPICON_NAME':'AppIcon','PRODUCT_BUNDLE_IDENTIFIER':'app.veritas.heartecho','CURRENT_PROJECT_VERSION':'5','MARKETING_VERSION':'0.4.0','CODE_SIGN_ENTITLEMENTS':'HeartEchoApp/HeartEchoApp.entitlements','TARGETED_DEVICE_FAMILY':'1','IPHONEOS_DEPLOYMENT_TARGET':'17.0','SUPPORTED_PLATFORMS':'iphoneos iphonesimulator','SUPPORTS_MACCATALYST':'NO','INFOPLIST_KEY_CFBundleDisplayName':'Heart Echo','INFOPLIST_KEY_LSApplicationCategoryType':'public.app-category.healthcare-fitness','INFOPLIST_KEY_UILaunchScreen_Generation':'YES','INFOPLIST_KEY_UIApplicationSceneManifest_Generation':'YES','INFOPLIST_KEY_UIApplicationSupportsIndirectInputEvents':'YES','INFOPLIST_KEY_UISupportedInterfaceOrientations':'UIInterfaceOrientationPortrait','INFOPLIST_KEY_NSMicrophoneUsageDescription':'Heart Echo records heart sounds for on-device BPM and murmur exploration. Audio is kept on this device only when you choose to retain it. Raw audio stays on this iPhone.','INFOPLIST_KEY_NSLocalNetworkUsageDescription':'Connect to your chosen Heart Echo care service on the same trusted Wi-Fi. Audio stays on this iPhone.','INFOPLIST_FILE':'HeartEchoApp/Info.plist','INFOPLIST_KEY_NSMotionUsageDescription':'Heart Echo uses phone motion to help identify handling noise while listening.','INFOPLIST_KEY_NSHealthShareUsageDescription':'Coordinate an optional heart-rate comparison with your paired Apple Watch.','INFOPLIST_KEY_NSHealthUpdateUsageDescription':'Ask the Watch to start a temporary measurement session. Workouts are discarded.'}
objects[main]={'isa':'PBXNativeTarget','name':'HeartEchoApp','productName':'HeartEchoApp','productReference':products[0],'productType':'com.apple.product-type.application','buildConfigurationList':configs('app',app),'buildPhases':[phase('appsource','PBXSourcesBuildPhase',[build(r,'app') for r in ui+engine]),phase('appframework','PBXFrameworksBuildPhase',[]),phase('appresource','PBXResourcesBuildPhase',[build(r,'resource') for r in models+[samples,assets]]),embed],'buildRules':[],'dependencies':[dependency]}
wconfig={**base,'PRODUCT_NAME':'HeartEchoWatch','PRODUCT_BUNDLE_IDENTIFIER':'app.veritas.heartecho.watchkitapp','SDKROOT':'watchos','SUPPORTED_PLATFORMS':'watchos watchsimulator','TARGETED_DEVICE_FAMILY':'4','WATCHOS_DEPLOYMENT_TARGET':'10.0','CURRENT_PROJECT_VERSION':'5','MARKETING_VERSION':'0.4.0','INFOPLIST_FILE':'Watch/Info.plist','INFOPLIST_KEY_CFBundleDisplayName':'Heart Echo','CODE_SIGN_ENTITLEMENTS':'Watch/Watch.entitlements'}
objects[watch]={'isa':'PBXNativeTarget','name':'HeartEchoWatch','productName':'HeartEchoWatch','productReference':products[1],'productType':'com.apple.product-type.application','buildConfigurationList':configs('watch',wconfig),'buildPhases':[phase('watchsource','PBXSourcesBuildPhase',[build(r,'watch') for r in [watchsrc]+shared]),phase('watchframework','PBXFrameworksBuildPhase',[]),phase('watchresource','PBXResourcesBuildPhase',[])],'buildRules':[],'dependencies':[]}
tproxy=obj('testproxy','PBXContainerItemProxy',containerPortal=project,proxyType='1',remoteGlobalIDString=main,remoteInfo='HeartEchoApp')
tdep=obj('testdependency','PBXTargetDependency',target=main,targetProxy=tproxy)
tconfig={**base,'PRODUCT_BUNDLE_IDENTIFIER':'app.veritas.heartecho.uitests','TEST_TARGET_NAME':'HeartEchoApp','IPHONEOS_DEPLOYMENT_TARGET':'17.0','TARGETED_DEVICE_FAMILY':'1'}
objects[test]={'isa':'PBXNativeTarget','name':'HeartEchoUITests','productName':'HeartEchoUITests','productReference':products[2],'productType':'com.apple.product-type.bundle.ui-testing','buildConfigurationList':configs('test',tconfig),'buildPhases':[phase('testsource','PBXSourcesBuildPhase',[build(r,'test') for r in tests]),phase('testframework','PBXFrameworksBuildPhase',[])],'buildRules':[],'dependencies':[tdep]}
pg=obj('products','PBXGroup',name='Products',sourceTree='<group>',children=products)
groups=[]
for name,refs in [('App',ui),('Engine',engine),('Models and Samples',models+[samples,assets]),('Watch',[watchsrc,file('Watch/Info.plist','text.plist.xml'),file('Watch/Watch.entitlements','text.plist.entitlements')]),('UI Tests',tests)]: groups.append(obj('group:'+name,'PBXGroup',name=name,sourceTree='<group>',children=refs))
root=obj('root','PBXGroup',sourceTree='<group>',children=groups+[pg])
pconfig={'CLANG_ENABLE_MODULES':'YES','SDKROOT':'iphoneos','IPHONEOS_DEPLOYMENT_TARGET':'17.0','SWIFT_VERSION':'5.0'}
objects[project]={'isa':'PBXProject','attributes':{'BuildIndependentTargetsInParallel':'YES','LastUpgradeCheck':'2720','TargetAttributes':{main:{'CreatedOnToolsVersion':'27.2','ProvisioningStyle':'Automatic'},watch:{'CreatedOnToolsVersion':'27.2','ProvisioningStyle':'Automatic'}}},'buildConfigurationList':configs('project',pconfig,{'SWIFT_OPTIMIZATION_LEVEL':'-Onone','DEBUG_INFORMATION_FORMAT':'dwarf','SWIFT_ACTIVE_COMPILATION_CONDITIONS':'DEBUG'},{'SWIFT_COMPILATION_MODE':'wholemodule','SWIFT_OPTIMIZATION_LEVEL':'-O','DEBUG_INFORMATION_FORMAT':'dwarf-with-dsym'}),'compatibilityVersion':'Xcode 14.0','developmentRegion':'en','knownRegions':['en','Base'],'mainGroup':root,'productRefGroup':pg,'projectDirPath':'','projectRoot':'','targets':[main,watch,test]}
def encode(value):
    if isinstance(value,dict): return '{\n'+''.join(json.dumps(k)+' = '+encode(v)+';\n' for k,v in value.items())+'}'
    if isinstance(value,list): return '('+','.join(encode(v) for v in value)+')'
    return json.dumps(value)
(ROOT/'HeartEchoApp.xcodeproj/project.pbxproj').write_text('// !$*UTF8*$!\n'+encode({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':project})+'\n')
p=ROOT/'HeartEchoApp.xcodeproj/xcshareddata/xcschemes/HeartEchoApp.xcscheme'
scheme=ET.parse(p);tree=scheme.getroot();previous=tree.find('TestAction')
if previous is not None: tree.remove(previous)
action=ET.SubElement(tree,'TestAction',{'buildConfiguration':'Debug','selectedDebuggerIdentifier':'Xcode.DebuggerFoundation.Debugger.LLDB','selectedLauncherIdentifier':'Xcode.IDEFoundation.Launcher.LLDB','shouldUseLaunchSchemeArgsEnv':'YES'})
item=ET.SubElement(ET.SubElement(action,'Testables'),'TestableReference',{'skipped':'NO','parallelizable':'NO'})
ET.SubElement(item,'BuildableReference',{'BuildableIdentifier':'primary','BlueprintIdentifier':test,'BuildableName':'HeartEchoUITests.xctest','BlueprintName':'HeartEchoUITests','ReferencedContainer':'container:HeartEchoApp.xcodeproj'})
ET.indent(scheme);scheme.write(p,encoding='unicode',xml_declaration=True)
print('Generated standalone iPhone, Watch and UI-test targets.')
