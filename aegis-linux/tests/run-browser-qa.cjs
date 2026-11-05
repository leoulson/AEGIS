const {spawn}=require('child_process');
const path=require('path');
const fixture=spawn('python3',[path.join(__dirname,'serve_update_fixture.py')],{stdio:['ignore','pipe','inherit']});
let received='',started=false;
const timeout=setTimeout(()=>{fixture.kill();throw Error('Fixture startup timed out');},30000);
fixture.stdout.on('data',chunk=>{
 received+=chunk;
 if(started||!received.includes('\n'))return;
 started=true;clearTimeout(timeout);
 const info=JSON.parse(received.split('\n')[0]);
 const test=spawn(process.execPath,[path.join(__dirname,'verify-interface.cjs')],{stdio:'inherit',env:{...process.env,AEGIS_TEST_FIXTURE:JSON.stringify(info)}});
 test.on('exit',code=>{fixture.kill();process.exitCode=code??1;});
 test.on('error',()=>{fixture.kill();process.exitCode=1;});
});
fixture.on('exit',code=>{if(!started){clearTimeout(timeout);process.exitCode=code||1;}});
