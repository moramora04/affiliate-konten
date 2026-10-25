(async()=>{
const P='https://moramora04.github.io';
if(!location.hostname.includes('facebook.com')){alert('Buka facebook.com dulu, lalu klik bookmark ini lagi.');return;}
const s=ms=>new Promise(r=>setTimeout(r,ms));
const dlg=()=>[...document.querySelectorAll('div[role=dialog]')].pop();
const inp=()=>document.querySelector('div[role=dialog] input[type=file][accept*=video]');
if(!inp()){alert('Halaman Buat Reel akan dibuka. Setelah terbuka, klik bookmark ini lagi.');location.href='https://www.facebook.com/reels/create';return;}
const w=window.open(P+'/affiliate-konten/reel.html','reelulang','width=430,height=680');
if(!w){alert('Popup diblokir. Izinkan popup untuk facebook.com lalu klik bookmark lagi.');return;}
let kode=null;
window.addEventListener('message',async e=>{
if(e.origin!==P||!e.data||e.data.type!=='reel'||kode!==null)return;
kode=e.data.kode;
const f=new File([e.data.blob],'reel-'+kode+'.mp4',{type:'video/mp4'});
const dt=new DataTransfer();dt.items.add(f);
const i=inp();i.files=dt.files;i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}));
let ok=false;
for(let n=0;n<120&&!ok;n++){
await s(1500);
const d=dlg();if(!d)continue;
const ed=d.querySelector('div[contenteditable=true][role=textbox]');
if(ed){
ed.focus();document.execCommand('selectAll');ed.dispatchEvent(new InputEvent('beforeinput',{inputType:'deleteContentBackward',bubbles:true,cancelable:true}));await s(300);
const c=new DataTransfer();c.setData('text/plain',e.data.caption);ed.dispatchEvent(new ClipboardEvent('paste',{clipboardData:c,bubbles:true,cancelable:true}));
await s(500);
const ai=d.querySelector('input[aria-label="Tambahkan Label AI"]');if(ai&&!ai.checked)ai.click();
ok=true;break;}
const b=[...d.querySelectorAll('div[role=button]')].find(x=>x.innerText.trim()==='Berikutnya'&&x.getAttribute('aria-disabled')!=='true');
if(b)b.click();
}
if(!ok){alert('Kolom deskripsi tidak muncul. Lanjutkan manual: klik Berikutnya, tempel caption dari jendela kecil.');return;}
document.addEventListener('click',ev=>{const b=ev.target.closest&&ev.target.closest('[role=button]');if(b&&b.innerText.trim()==='Posting'&&b.closest('div[role=dialog]')){try{w.postMessage({type:'done',kode},P);}catch(x){}}},true);
alert('Kode '+kode+' siap. Cek video, caption, dan Label AI, lalu klik Posting.');
});
})();
